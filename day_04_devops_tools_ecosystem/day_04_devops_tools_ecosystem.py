"""
DEVOPS TOOLS ECOSYSTEM
Git, Linux, Bash, Docker, Jenkins, GitHub Actions, Terraform, Kubernetes

This script is written as an executable learning document. It introduces the
major components of a modern DevOps ecosystem from basic concepts to advanced
implementation patterns.

The script is intentionally self-contained. Most sections demonstrate concepts
using Python print statements, generated examples, diagrams, configuration
snippets, command references, and conceptual simulations.

Some commands shown in strings require the relevant tools to be installed if
they are executed outside this educational script.
"""


# =============================================================================
# 1. INTRODUCTION TO THE DEVOPS TOOLS ECOSYSTEM
# =============================================================================

print("\n" + "=" * 90)
print("DEVOPS TOOLS ECOSYSTEM")
print("=" * 90)

print("""
DevOps is a collection of engineering practices, cultural principles, automation
techniques, and operational processes intended to improve the way software is
built, tested, delivered, deployed, and operated.

DevOps is not a single programming language, framework, or product.

A typical software delivery lifecycle contains several interconnected stages:

    PLAN
      |
      v
    DEVELOP
      |
      v
    BUILD
      |
      v
    TEST
      |
      v
    RELEASE
      |
      v
    DEPLOY
      |
      v
    OPERATE
      |
      v
    MONITOR
      |
      +---------------------> Feedback returns to planning and development

The DevOps tools ecosystem provides specialized tools for these stages.

A representative mapping is:

    SOURCE CODE MANAGEMENT
        Git + GitHub

    OPERATING SYSTEM ENVIRONMENT
        Linux

    AUTOMATION AND SCRIPTING
        Bash

    APPLICATION PACKAGING
        Docker

    CONTINUOUS INTEGRATION / CONTINUOUS DELIVERY
        Jenkins
        GitHub Actions

    INFRASTRUCTURE AS CODE
        Terraform

    CONTAINER ORCHESTRATION
        Kubernetes

These tools are not isolated technologies. They usually work together.
""")


# =============================================================================
# 2. THE COMPLETE DEVOPS PIPELINE
# =============================================================================

print("\n" + "=" * 90)
print("2. A TYPICAL DEVOPS DELIVERY PIPELINE")
print("=" * 90)

devops_pipeline = [
    ("1", "Developer writes application code"),
    ("2", "Git tracks changes locally"),
    ("3", "Changes are pushed to a remote repository"),
    ("4", "CI pipeline is triggered"),
    ("5", "Application is built"),
    ("6", "Automated tests are executed"),
    ("7", "Docker image is created"),
    ("8", "Docker image is stored in a registry"),
    ("9", "Terraform provisions or updates infrastructure"),
    ("10", "Kubernetes deploys and manages containers"),
    ("11", "Application runs in the production environment"),
    ("12", "Monitoring and operational feedback influence future development"),
]

for number, stage in devops_pipeline:
    print(f"{number:>3}. {stage}")

print("""
A modern implementation can be represented as:

Developer
    |
    v
Git Repository
    |
    v
GitHub / Git Server
    |
    +------------------------------+
    |                              |
    v                              v
GitHub Actions                  Jenkins
    |                              |
    +--------------+---------------+
                   |
                   v
             Build + Test
                   |
                   v
             Docker Image
                   |
                   v
           Container Registry
                   |
                   v
             Terraform
                   |
                   v
         Cloud / Infrastructure
                   |
                   v
             Kubernetes
                   |
                   v
             Running Application
""")


# =============================================================================
# 3. GIT
# =============================================================================

print("\n" + "=" * 90)
print("3. GIT: DISTRIBUTED VERSION CONTROL")
print("=" * 90)

print("""
Git is a distributed version control system.

Version control allows developers to:

- Track modifications.
- Compare versions.
- Restore previous versions.
- Work in parallel.
- Merge independent changes.
- Maintain a history of software development.
- Collaborate through remote repositories.

Git distinguishes between several important locations:

    WORKING DIRECTORY
        The files currently being edited.

             |
             | git add
             v

    STAGING AREA / INDEX
        The changes selected for the next commit.

             |
             | git commit
             v

    LOCAL REPOSITORY
        The local history stored by Git.

             |
             | git push
             v

    REMOTE REPOSITORY
        Shared repository hosted on GitHub, GitLab, Bitbucket, or another server.
""")

git_workflow = [
    ("git init", "Create a new Git repository"),
    ("git clone", "Copy an existing repository"),
    ("git status", "Display repository status"),
    ("git add", "Add changes to the staging area"),
    ("git commit", "Create a permanent version"),
    ("git log", "View commit history"),
    ("git diff", "Compare changes"),
    ("git branch", "Manage branches"),
    ("git switch", "Move between branches"),
    ("git merge", "Combine histories"),
    ("git pull", "Fetch and integrate remote changes"),
    ("git push", "Upload commits to a remote"),
    ("git fetch", "Download remote information without integrating"),
]

for command, purpose in git_workflow:
    print(f"{command:<20} -> {purpose}")


# -----------------------------------------------------------------------------
# 3.1 Git Commit Model
# -----------------------------------------------------------------------------

print("\nGIT COMMIT MODEL\n")

print("""
A Git commit is a snapshot reference.

A simplified commit history:

    A --- B --- C --- D

Each commit contains metadata and references to its parent.

Example:

    Commit D
       |
       v
    Commit C
       |
       v
    Commit B
       |
       v
    Commit A

Git identifies commits using cryptographic hashes.

Example:

    8f3d1a7c4e...

The commit hash represents the content and structure associated with that
commit. Changing historical content generally changes the resulting hashes.
""")


# -----------------------------------------------------------------------------
# 3.2 Git Branching
# -----------------------------------------------------------------------------

print("\nGIT BRANCHING\n")

print("""
Branches allow independent lines of development.

Initial history:

    main

    A --- B --- C


Create a feature branch:

    git switch -c feature/login


History becomes:

               D --- E
              /
    A --- B --- C
              \
               main


After merging:

    A --- B --- C -------- M
              \          /
               D --- E


Common branch categories include:

    main
        Stable production-oriented branch.

    develop
        Integration branch in some branching strategies.

    feature/*
        New functionality.

    bugfix/*
        Non-production bug fixes.

    hotfix/*
        Urgent production fixes.

Branching strategy depends on organizational requirements. GitFlow, trunk-based
development, and GitHub Flow represent different approaches.
""")


# -----------------------------------------------------------------------------
# 3.3 Merge and Rebase
# -----------------------------------------------------------------------------

print("\nMERGE VS REBASE\n")

print("""
MERGE preserves branch history.

Example:

    git switch main
    git merge feature/login


REBASING rewrites a branch so that it appears to begin from a newer base.

Example:

    git switch feature/login
    git rebase main


Original history:

        F1 --- F2
       /
A --- B --- C


After merge:

        F1 --- F2
       /          \\
A --- B --- C ----- M


After rebase:

A --- B --- C --- F1' --- F2'


Rebase can produce a cleaner linear history, but rewriting published history can
cause problems for collaborators. A common operational rule is to avoid rebasing
public branches unless the team's workflow explicitly permits it.
""")


# -----------------------------------------------------------------------------
# 3.4 Merge Conflicts
# -----------------------------------------------------------------------------

print("\nMERGE CONFLICTS\n")

conflict_example = """
<<<<<<< HEAD
port = 8000
=======
port = 8080
>>>>>>> feature/config-update
"""

print(conflict_example)

print("""
A merge conflict occurs when Git cannot automatically determine which version of
a modification should be retained.

The developer resolves the conflict manually:

    port = 8080

Then stages and commits the resolution.

Important commands:

    git status
    git diff
    git add <file>
    git commit
""")


# =============================================================================
# 4. LINUX
# =============================================================================

print("\n" + "=" * 90)
print("4. LINUX: THE FOUNDATION OF MANY DEVOPS ENVIRONMENTS")
print("=" * 90)

print("""
Linux is central to modern infrastructure because servers, containers, cloud
instances, CI runners, Kubernetes nodes, and developer environments frequently
run Linux.

Understanding Linux requires familiarity with:

- File systems
- Processes
- Users and permissions
- Networking
- Package management
- Services
- Logs
- Environment variables
- Shells
""")


# -----------------------------------------------------------------------------
# 4.1 Linux File System
# -----------------------------------------------------------------------------

print("\nLINUX FILE SYSTEM\n")

linux_directories = {
    "/": "Root of the filesystem",
    "/home": "User home directories",
    "/root": "Home directory of the root user",
    "/etc": "System configuration",
    "/var": "Variable data, logs, caches and application data",
    "/tmp": "Temporary files",
    "/usr": "User programs and libraries",
    "/bin": "Essential command binaries",
    "/sbin": "System administration binaries",
    "/opt": "Optional third-party software",
    "/proc": "Virtual filesystem exposing process and kernel information",
    "/dev": "Device files",
    "/mnt": "Temporary mount points",
}

for directory, purpose in linux_directories.items():
    print(f"{directory:<10} -> {purpose}")


# -----------------------------------------------------------------------------
# 4.2 Linux Commands
# -----------------------------------------------------------------------------

print("\nCOMMON LINUX COMMANDS\n")

linux_commands = [
    ("pwd", "Show current directory"),
    ("ls", "List files"),
    ("ls -la", "Detailed list including hidden files"),
    ("cd", "Change directory"),
    ("mkdir", "Create directory"),
    ("touch", "Create an empty file"),
    ("cp", "Copy files"),
    ("mv", "Move or rename files"),
    ("rm", "Remove files"),
    ("rm -r", "Remove directories recursively"),
    ("cat", "Display file contents"),
    ("less", "Read large files interactively"),
    ("grep", "Search text"),
    ("find", "Search files"),
    ("head", "Display beginning of a file"),
    ("tail", "Display end of a file"),
    ("tail -f", "Follow a changing file"),
]

for command, purpose in linux_commands:
    print(f"{command:<15} -> {purpose}")


# -----------------------------------------------------------------------------
# 4.3 Linux Permissions
# -----------------------------------------------------------------------------

print("\nLINUX PERMISSIONS\n")

print("""
A typical permission representation:

    -rwxr-xr--

Breakdown:

    -          File type
    rwx        Owner permissions
    r-x        Group permissions
    r--        Other user permissions

Permissions:

    r = read
    w = write
    x = execute


Numeric representation:

    read    = 4
    write   = 2
    execute = 1


Examples:

    7 = rwx = 4 + 2 + 1
    6 = rw- = 4 + 2
    5 = r-x = 4 + 1
    4 = r-- = 4


Therefore:

    chmod 755 script.sh

means:

    Owner  = rwx
    Group  = r-x
    Others = r-x


Another example:

    chmod 600 secret.txt

means:

    Owner  = rw-
    Group  = ---
    Others = ---
""")


# -----------------------------------------------------------------------------
# 4.4 Processes
# -----------------------------------------------------------------------------

print("\nLINUX PROCESSES\n")

print("""
Every running program is represented by one or more processes.

Useful commands:

    ps
        Display processes.

    ps aux
        Detailed process listing.

    top
        Interactive process monitoring.

    htop
        Enhanced interactive monitoring when installed.

    kill PID
        Send a signal to a process.

    kill -9 PID
        Send SIGKILL.

Common signals:

    SIGTERM
        Request graceful termination.

    SIGKILL
        Force termination.

    SIGHUP
        Historically associated with terminal disconnects and commonly used
        for configuration reload behavior.

A production system should generally prefer graceful termination before forced
termination whenever the application supports it.
""")


# -----------------------------------------------------------------------------
# 4.5 Services and systemd
# -----------------------------------------------------------------------------

print("\nSYSTEMD SERVICES\n")

print("""
Many modern Linux distributions use systemd.

Useful commands:

    systemctl status nginx
    systemctl start nginx
    systemctl stop nginx
    systemctl restart nginx
    systemctl enable nginx
    systemctl disable nginx


A service unit may resemble:

    [Unit]
    Description=Example Application

    [Service]
    ExecStart=/usr/bin/python3 /opt/app/main.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
""")


# =============================================================================
# 5. BASH
# =============================================================================

print("\n" + "=" * 90)
print("5. BASH: AUTOMATION THROUGH SHELL SCRIPTING")
print("=" * 90)

print("""
Bash is a shell and scripting language commonly used in Linux environments.

DevOps engineers use Bash to automate:

- Deployment tasks
- File processing
- Environment setup
- Log analysis
- CI pipeline commands
- Server administration
- Build operations
- Health checks
""")


# -----------------------------------------------------------------------------
# 5.1 Basic Bash Script
# -----------------------------------------------------------------------------

print("\nBASIC BASH SCRIPT\n")

bash_example = r"""#!/usr/bin/env bash

NAME="DevOps"

echo "Hello, $NAME"
"""

print(bash_example)

print("""
The shebang:

    #!/usr/bin/env bash

indicates that the script should be executed using Bash.

Variables are commonly assigned without spaces:

    NAME="DevOps"

Referenced with:

    $NAME

or:

    ${NAME}
""")


# -----------------------------------------------------------------------------
# 5.2 Bash Variables and Environment Variables
# -----------------------------------------------------------------------------

print("\nBASH VARIABLES\n")

print(r"""
Local shell variable:

    VERSION="1.0.0"


Environment variable:

    export VERSION="1.0.0"


Access:

    echo "$VERSION"


Environment variables are inherited by child processes. This distinction matters
when scripts launch applications, containers, build tools, or other commands.
""")


# -----------------------------------------------------------------------------
# 5.3 Conditions
# -----------------------------------------------------------------------------

print("\nBASH CONDITIONS\n")

bash_condition = r"""#!/usr/bin/env bash

ENVIRONMENT="${1:-development}"

if [ "$ENVIRONMENT" = "production" ]; then
    echo "Deploying to production"
else
    echo "Deploying to non-production environment"
fi
"""

print(bash_condition)


# -----------------------------------------------------------------------------
# 5.4 Loops
# -----------------------------------------------------------------------------

print("\nBASH LOOPS\n")

bash_loop = r"""for service in api frontend worker
do
    echo "Checking $service"
done
"""

print(bash_loop)


# -----------------------------------------------------------------------------
# 5.5 Exit Codes
# -----------------------------------------------------------------------------

print("\nBASH EXIT CODES\n")

print("""
Unix commands communicate success and failure using exit codes.

Conventionally:

    0
        Success

    Non-zero
        Failure

Example:

    command
    echo $?


The special variable $? contains the exit status of the previous command.

In automation, exit codes are essential because CI/CD systems determine whether
a build, test, or deployment step succeeded based on command results.
""")


# -----------------------------------------------------------------------------
# 5.6 Defensive Bash
# -----------------------------------------------------------------------------

print("\nDEFENSIVE BASH\n")

print(r"""
A common pattern is:

    set -euo pipefail


-e
    Exit when a command fails.

-u
    Treat undefined variables as errors.

-o pipefail
    Cause a pipeline to fail if any important command within it fails.


Example:

    #!/usr/bin/env bash
    set -euo pipefail

    echo "Building application"
    python -m pytest

    echo "Tests completed"
""")


# =============================================================================
# 6. DOCKER
# =============================================================================

print("\n" + "=" * 90)
print("6. DOCKER: APPLICATION CONTAINERIZATION")
print("=" * 90)

print("""
Docker packages applications and their dependencies into containers.

A container provides process isolation and a predictable runtime environment.

Traditional deployment:

    Application
        |
        v
    Dependencies installed directly on server
        |
        v
    Operating System


Containerized deployment:

    Application
        |
        v
    Container Image
        |
        v
    Container Runtime
        |
        v
    Host Operating System


Containers share the host kernel but isolate processes and filesystem views.

A container is not the same as a traditional virtual machine.

Virtual machine:

    Application
    Dependencies
    Guest OS
    Hypervisor
    Host OS
    Hardware


Container:

    Application
    Dependencies
    Container Runtime
    Host OS
    Hardware
""")


# -----------------------------------------------------------------------------
# 6.1 Docker Images and Containers
# -----------------------------------------------------------------------------

print("\nDOCKER IMAGE VS CONTAINER\n")

print("""
IMAGE
    A packaged, immutable template.

CONTAINER
    A running instance of an image.

Example:

    Image:
        nginx:latest

    Running container:
        container-id -> created from nginx:latest
""")


# -----------------------------------------------------------------------------
# 6.2 Dockerfile
# -----------------------------------------------------------------------------

print("\nDOCKERFILE\n")

dockerfile = r"""FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
"""

print(dockerfile)

print("""
Important instructions:

FROM
    Selects the base image.

WORKDIR
    Sets the working directory.

COPY
    Copies files into the image.

RUN
    Executes commands while building the image.

EXPOSE
    Documents an intended network port.

CMD
    Defines the default command executed by the container.
""")


# -----------------------------------------------------------------------------
# 6.3 Docker Build and Run
# -----------------------------------------------------------------------------

print("\nDOCKER COMMANDS\n")

docker_commands = [
    ("docker build -t myapp:1.0 .", "Build an image"),
    ("docker images", "List local images"),
    ("docker run myapp:1.0", "Run a container"),
    ("docker ps", "List running containers"),
    ("docker ps -a", "List all containers"),
    ("docker logs <container>", "View container logs"),
    ("docker exec -it <container> sh", "Open a shell"),
    ("docker stop <container>", "Stop a container"),
    ("docker rm <container>", "Remove a container"),
    ("docker rmi <image>", "Remove an image"),
]

for command, purpose in docker_commands:
    print(f"{command:<45} -> {purpose}")


# -----------------------------------------------------------------------------
# 6.4 Docker Layers and Build Cache
# -----------------------------------------------------------------------------

print("\nDOCKER LAYERS\n")

print("""
Docker images are commonly composed of layers.

Example:

    FROM python:3.12
        |
        v
    COPY requirements.txt
        |
        v
    RUN pip install
        |
        v
    COPY application source
        |
        v
    Final image


Layer ordering affects build performance.

This is generally inefficient:

    COPY . .
    RUN pip install -r requirements.txt


Any source-code modification may invalidate the dependency installation layer.

A better approach is:

    COPY requirements.txt .
    RUN pip install -r requirements.txt
    COPY . .

Dependency installation can then be reused when application source changes but
the dependency file remains unchanged.
""")


# -----------------------------------------------------------------------------
# 6.5 Docker Networking
# -----------------------------------------------------------------------------

print("\nDOCKER NETWORKING\n")

print("""
Containers can communicate through Docker networks.

Example:

    docker network create application-network


Services:

    frontend
    api
    database


Within the same Docker network, services can often communicate using service
or container DNS names.

Example conceptual request:

    api -> database:5432


Port publishing:

    docker run -p 8080:8000 myapp


This maps:

    Host port 8080
            |
            v
    Container port 8000
""")


# -----------------------------------------------------------------------------
# 6.6 Volumes
# -----------------------------------------------------------------------------

print("\nDOCKER VOLUMES\n")

print("""
Containers are designed to be disposable.

Persistent data should usually be stored outside the container's writable layer.

Example:

    docker volume create postgres-data

    docker run \
        -v postgres-data:/var/lib/postgresql/data \
        postgres


A volume allows persistent data to survive container recreation.
""")


# =============================================================================
# 7. JENKINS
# =============================================================================

print("\n" + "=" * 90)
print("7. JENKINS: CONTINUOUS INTEGRATION AND DELIVERY")
print("=" * 90)

print("""
Jenkins is an automation server frequently used for CI/CD.

A Jenkins pipeline can:

- Retrieve source code.
- Install dependencies.
- Build software.
- Run tests.
- Perform security checks.
- Build Docker images.
- Push images to registries.
- Deploy applications.
- Trigger infrastructure operations.

A simplified flow:

Git Push
   |
   v
Jenkins Trigger
   |
   v
Checkout
   |
   v
Build
   |
   v
Test
   |
   v
Package
   |
   v
Deploy
""")


# -----------------------------------------------------------------------------
# 7.1 Jenkins Pipeline
# -----------------------------------------------------------------------------

print("\nJENKINS PIPELINE\n")

jenkins_pipeline = r"""pipeline {
    agent any

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh 'python -m pip install -r requirements.txt'
            }
        }

        stage('Test') {
            steps {
                sh 'python -m pytest'
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t myapp:${BUILD_NUMBER} .'
            }
        }
    }
}
"""

print(jenkins_pipeline)


# -----------------------------------------------------------------------------
# 7.2 Declarative Pipeline
# -----------------------------------------------------------------------------

print("\nJENKINS PIPELINE STRUCTURE\n")

print("""
A declarative pipeline commonly contains:

pipeline
    |
    +-- agent
    |
    +-- environment
    |
    +-- options
    |
    +-- stages
    |      |
    |      +-- stage
    |             |
    |             +-- steps
    |
    +-- post


Example environment variables:

    environment {
        IMAGE_NAME = "myapp"
        REGISTRY = "registry.example.com"
    }


Post actions can define behavior such as:

    post {
        success {
            echo 'Pipeline succeeded'
        }

        failure {
            echo 'Pipeline failed'
        }

        always {
            cleanWs()
        }
    }
""")


# -----------------------------------------------------------------------------
# 7.3 Jenkins Agents
# -----------------------------------------------------------------------------

print("\nJENKINS AGENTS\n")

print("""
The Jenkins controller coordinates automation.

Agents execute jobs.

Architecture:

                    Jenkins Controller
                           |
              +------------+------------+
              |            |            |
              v            v            v
          Agent 1       Agent 2       Agent 3
           Linux         Docker        Windows
           Python        Java          .NET


Different workloads may require different environments.

A Docker build may execute on an agent with Docker access.

A Windows application may execute on a Windows agent.

A Kubernetes-based Jenkins setup can dynamically create build agents as pods.
""")


# =============================================================================
# 8. GITHUB ACTIONS
# =============================================================================

print("\n" + "=" * 90)
print("8. GITHUB ACTIONS: REPOSITORY-NATIVE AUTOMATION")
print("=" * 90)

print("""
GitHub Actions is a workflow automation platform integrated with GitHub.

Workflows are usually stored in:

    .github/workflows/


Workflow files are written in YAML.

Important concepts:

Workflow
    A complete automation definition.

Event
    An event that triggers automation.

Job
    A group of steps.

Step
    A single action or command.

Runner
    The environment that executes a job.

Action
    A reusable automation component.
""")


# -----------------------------------------------------------------------------
# 8.1 Basic GitHub Actions Workflow
# -----------------------------------------------------------------------------

print("\nGITHUB ACTIONS WORKFLOW\n")

github_actions_workflow = r"""name: Python CI

on:
  push:
    branches:
      - main

  pull_request:
    branches:
      - main

jobs:
  test:

    runs-on: ubuntu-latest

    steps:

      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run tests
        run: |
          pytest
"""

print(github_actions_workflow)


# -----------------------------------------------------------------------------
# 8.2 Events
# -----------------------------------------------------------------------------

print("\nGITHUB ACTIONS EVENTS\n")

print("""
Common triggers include:

    push
        Run when commits are pushed.

    pull_request
        Run when a pull request is created or updated.

    workflow_dispatch
        Manual execution.

    schedule
        Scheduled execution using cron syntax.

Example:

    on:
      schedule:
        - cron: "0 2 * * *"

This represents a scheduled workflow according to the configured cron schedule.
""")


# -----------------------------------------------------------------------------
# 8.3 Secrets
# -----------------------------------------------------------------------------

print("\nGITHUB ACTIONS SECRETS\n")

print("""
Credentials should not normally be hardcoded into workflow files.

Conceptually:

    secrets.DOCKER_USERNAME
    secrets.DOCKER_PASSWORD


Example:

    env:
      API_KEY: ${{ secrets.API_KEY }}


Secrets should be handled carefully because:

- Logs may expose command output.
- Debugging settings can reveal environment information.
- Third-party actions must be trusted.
- Pull request execution models require special attention.
""")


# -----------------------------------------------------------------------------
# 8.4 Matrix Builds
# -----------------------------------------------------------------------------

print("\nGITHUB ACTIONS MATRIX BUILDS\n")

matrix_example = r"""strategy:
  matrix:
    python-version:
      - "3.10"
      - "3.11"
      - "3.12"

steps:
  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python-version }}
"""

print(matrix_example)

print("""
Matrix strategies allow the same job to execute against multiple combinations.

Conceptually:

                Python 3.10
               /
Test Matrix -- Python 3.11
               \\
                Python 3.12
""")


# =============================================================================
# 9. TERRAFORM
# =============================================================================

print("\n" + "=" * 90)
print("9. TERRAFORM: INFRASTRUCTURE AS CODE")
print("=" * 90)

print("""
Terraform is an Infrastructure as Code tool.

Infrastructure can include:

- Virtual machines
- Networks
- Load balancers
- Databases
- DNS records
- Kubernetes resources
- Cloud services

Instead of manually creating infrastructure through a graphical interface,
infrastructure definitions can be stored as code.

Conceptually:

Manual infrastructure:

Engineer
    |
    v
Cloud Console
    |
    v
Click configuration
    |
    v
Infrastructure


Infrastructure as Code:

Terraform files
    |
    v
Version Control
    |
    v
terraform plan
    |
    v
terraform apply
    |
    v
Infrastructure
""")


# -----------------------------------------------------------------------------
# 9.1 Terraform Configuration
# -----------------------------------------------------------------------------

print("\nTERRAFORM CONFIGURATION EXAMPLE\n")

terraform_example = r"""terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
}

resource "aws_s3_bucket" "example" {
  bucket = "example-unique-bucket-name"
}
"""

print(terraform_example)


# -----------------------------------------------------------------------------
# 9.2 Terraform Lifecycle
# -----------------------------------------------------------------------------

print("\nTERRAFORM WORKFLOW\n")

terraform_commands = [
    ("terraform init", "Initialize providers and modules"),
    ("terraform fmt", "Format Terraform configuration"),
    ("terraform validate", "Validate configuration"),
    ("terraform plan", "Preview proposed changes"),
    ("terraform apply", "Create or modify infrastructure"),
    ("terraform destroy", "Remove managed infrastructure"),
]

for command, purpose in terraform_commands:
    print(f"{command:<25} -> {purpose}")


# -----------------------------------------------------------------------------
# 9.3 Desired State
# -----------------------------------------------------------------------------

print("\nTERRAFORM DESIRED STATE\n")

print("""
Terraform uses declarative configuration.

You describe the desired infrastructure state.

Example:

    Desired state:

        3 application servers


Terraform compares:

    Current state
            VS
    Desired state


Then determines required actions.

Current:

    2 servers

Desired:

    3 servers

Plan:

    + Create 1 server


This is different from writing an imperative sequence such as:

    Step 1: Log into cloud
    Step 2: Create server
    Step 3: Configure server
""")


# -----------------------------------------------------------------------------
# 9.4 Terraform State
# -----------------------------------------------------------------------------

print("\nTERRAFORM STATE\n")

print("""
Terraform maintains state information to map configuration resources to real
infrastructure.

A state file may contain relationships such as:

    aws_instance.application
        |
        v
    Actual cloud instance ID


State is operationally important.

Risks include:

- Sensitive information in state.
- Concurrent modifications.
- State corruption.
- Inconsistent ownership.

For teams, remote state storage and state locking are commonly used.

A conceptual shared architecture:

Terraform Users
       |
       v
Remote State Backend
       |
       +------ State Storage
       |
       +------ Locking Mechanism
""")


# -----------------------------------------------------------------------------
# 9.5 Terraform Modules
# -----------------------------------------------------------------------------

print("\nTERRAFORM MODULES\n")

print("""
Modules provide reusable infrastructure components.

Example structure:

modules/
    network/
    database/
    application/


Root configuration:

module "network" {
  source = "./modules/network"
}

module "database" {
  source = "./modules/database"
}


Modules improve:

- Reusability
- Standardization
- Maintainability
- Separation of concerns
""")


# =============================================================================
# 10. KUBERNETES
# =============================================================================

print("\n" + "=" * 90)
print("10. KUBERNETES: CONTAINER ORCHESTRATION")
print("=" * 90)

print("""
Kubernetes orchestrates containerized applications.

A container platform must solve problems such as:

- Scheduling workloads.
- Restarting failed applications.
- Scaling applications.
- Service discovery.
- Load balancing.
- Rolling updates.
- Configuration management.
- Secret management.

Kubernetes introduces an abstraction hierarchy.

Common structure:

Cluster
    |
    +-- Control Plane
    |
    +-- Worker Nodes
            |
            +-- Pods
                    |
                    +-- Containers
""")


# -----------------------------------------------------------------------------
# 10.1 Kubernetes Cluster Architecture
# -----------------------------------------------------------------------------

print("\nKUBERNETES ARCHITECTURE\n")

print("""
CONTROL PLANE

    API Server
        Entry point for cluster operations.

    Scheduler
        Determines where workloads should run.

    Controller Manager
        Maintains desired state through controllers.

    etcd
        Stores cluster state.


WORKER NODE

    kubelet
        Node agent responsible for managing workloads.

    Container Runtime
        Runs containers.

    kube-proxy or equivalent networking mechanisms
        Supports network connectivity and service behavior.
""")


# -----------------------------------------------------------------------------
# 10.2 Pods
# -----------------------------------------------------------------------------

print("\nKUBERNETES PODS\n")

print("""
A Pod is the smallest deployable Kubernetes unit.

A Pod can contain one or more containers.

Example:

Pod
    |
    +-- Application Container
    |
    +-- Sidecar Container


Containers in the same Pod can share:

- Network namespace
- localhost communication
- Storage volumes when configured

A Pod is not normally treated as a permanent individual server. Kubernetes can
replace Pods when workloads are rescheduled or restarted.
""")


# -----------------------------------------------------------------------------
# 10.3 Deployments
# -----------------------------------------------------------------------------

print("\nKUBERNETES DEPLOYMENTS\n")

deployment_yaml = r"""apiVersion: apps/v1
kind: Deployment

metadata:
  name: application

spec:
  replicas: 3

  selector:
    matchLabels:
      app: application

  template:

    metadata:
      labels:
        app: application

    spec:

      containers:

        - name: application
          image: example/application:1.0

          ports:
            - containerPort: 8000
"""

print(deployment_yaml)

print("""
A Deployment manages the desired number of application replicas.

Example:

replicas: 3


Kubernetes attempts to maintain:

    Pod 1 -> Running
    Pod 2 -> Running
    Pod 3 -> Running


If one Pod fails:

    Pod 2 -> Failed
                |
                v
    Controller creates replacement
                |
                v
    New Pod -> Running


This represents reconciliation toward the declared desired state.
""")


# -----------------------------------------------------------------------------
# 10.4 Services
# -----------------------------------------------------------------------------

print("\nKUBERNETES SERVICES\n")

service_yaml = r"""apiVersion: v1
kind: Service

metadata:
  name: application-service

spec:
  selector:
    app: application

  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000

  type: ClusterIP
"""

print(service_yaml)

print("""
Pods can be replaced and their individual IP addresses can change.

A Service provides a stable abstraction.

Client
   |
   v
Service
   |
   +-------- Pod A
   |
   +-------- Pod B
   |
   +-------- Pod C


Common Service types:

ClusterIP
    Internal cluster communication.

NodePort
    Exposes a port on cluster nodes.

LoadBalancer
    Integrates with supported external load balancing infrastructure.
""")


# -----------------------------------------------------------------------------
# 10.5 ConfigMaps and Secrets
# -----------------------------------------------------------------------------

print("\nCONFIGURATION MANAGEMENT\n")

print("""
Applications should generally separate code from environment-specific
configuration.

Examples:

    DATABASE_HOST
    API_URL
    FEATURE_FLAG


ConfigMaps store non-sensitive configuration.

Secrets are intended for sensitive configuration.

Conceptual pattern:

Application Code
       |
       +------ ConfigMap
       |
       +------ Secret
       |
       v
Runtime Configuration


Sensitive values still require careful protection. The existence of a Kubernetes
Secret object does not eliminate the need for access control, encryption,
credential rotation, and secure operational practices.
""")


# -----------------------------------------------------------------------------
# 10.6 Namespaces
# -----------------------------------------------------------------------------

print("\nKUBERNETES NAMESPACES\n")

print("""
Namespaces logically divide resources within a cluster.

Example:

    Cluster

        development namespace
            - application
            - database

        staging namespace
            - application
            - database

        production namespace
            - application
            - database


Namespaces support organization, access control policies, and resource
segmentation.
""")


# -----------------------------------------------------------------------------
# 10.7 Scaling
# -----------------------------------------------------------------------------

print("\nKUBERNETES SCALING\n")

print("""
Manual scaling:

    kubectl scale deployment application --replicas=5


Desired state:

    replicas: 5


Automatic scaling can use metrics through mechanisms such as Horizontal Pod
Autoscaling.

Conceptual model:

Traffic increases
       |
       v
Resource utilization increases
       |
       v
Autoscaler evaluates metrics
       |
       v
More Pods created


Traffic decreases
       |
       v
Utilization decreases
       |
       v
Autoscaler reduces replicas when configured thresholds permit it.
""")


# -----------------------------------------------------------------------------
# 10.8 Rolling Updates
# -----------------------------------------------------------------------------

print("\nKUBERNETES ROLLING UPDATES\n")

print("""
Suppose the application currently runs:

    Version 1.0

with three replicas.

Current:

    Pod A -> 1.0
    Pod B -> 1.0
    Pod C -> 1.0


Deploy Version 1.1.

Kubernetes can progressively replace instances:

    Pod A -> 1.1
    Pod B -> 1.0
    Pod C -> 1.0

Then:

    Pod A -> 1.1
    Pod B -> 1.1
    Pod C -> 1.0

Finally:

    Pod A -> 1.1
    Pod B -> 1.1
    Pod C -> 1.1


Deployment strategies can define:

    maxSurge
    maxUnavailable


These settings influence how capacity is maintained during rollout.
""")


# =============================================================================
# 11. THE TOOLS WORKING TOGETHER
# =============================================================================

print("\n" + "=" * 90)
print("11. INTEGRATED DEVOPS TOOLCHAIN")
print("=" * 90)

print("""
A practical system can combine all of the tools discussed.

Example application lifecycle:

1. Developer writes code.

2. Development occurs in a Linux environment.

3. Bash scripts automate repetitive tasks.

4. Git tracks source code.

5. Code is pushed to GitHub.

6. GitHub Actions or Jenkins starts a CI pipeline.

7. Dependencies are installed.

8. Tests are executed.

9. Docker packages the application.

10. The Docker image is pushed to a registry.

11. Terraform provisions infrastructure.

12. Kubernetes receives the new deployment definition.

13. Kubernetes pulls the application image.

14. Kubernetes schedules Pods.

15. Services provide stable networking.

16. Controllers maintain the desired number of replicas.
""")


# =============================================================================
# 12. COMPLETE ARCHITECTURE EXAMPLE
# =============================================================================

print("\n" + "=" * 90)
print("12. COMPLETE ARCHITECTURE EXAMPLE")
print("=" * 90)

print("""
                           DEVELOPER
                               |
                               v
                         Linux + Bash
                               |
                               v
                              Git
                               |
                               v
                            GitHub
                               |
                    Push / Pull Request Event
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
          GitHub Actions                  Jenkins
                 |                           |
                 +-------------+-------------+
                               |
                               v
                         Build Application
                               |
                               v
                           Run Tests
                               |
                               v
                         Docker Build
                               |
                               v
                       Container Registry
                               |
                               v
                        Terraform Apply
                               |
                               v
                   Cloud Infrastructure
                               |
                               v
                      Kubernetes Cluster
                               |
                               v
                         Deployment
                               |
                               v
                         ReplicaSet
                               |
                               v
                         Application Pods
                               |
                               v
                            Service
                               |
                               v
                            Users
""")


# =============================================================================
# 13. END-TO-END EXAMPLE PROJECT STRUCTURE
# =============================================================================

print("\n" + "=" * 90)
print("13. END-TO-END PROJECT STRUCTURE")
print("=" * 90)

project_structure = """
project/

├── app/
│   ├── main.py
│   └── requirements.txt
│
├── tests/
│   └── test_main.py
│
├── scripts/
│   ├── build.sh
│   └── deploy.sh
│
├── infrastructure/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
│
├── kubernetes/
│   ├── deployment.yaml
│   └── service.yaml
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── Dockerfile
├── Jenkinsfile
└── README.md
"""

print(project_structure)


# =============================================================================
# 14. BUILD SCRIPT EXAMPLE
# =============================================================================

print("\n" + "=" * 90)
print("14. BUILD AUTOMATION EXAMPLE")
print("=" * 90)

build_script = r"""#!/usr/bin/env bash

set -euo pipefail

IMAGE_NAME="example/application"
IMAGE_TAG="${1:-latest}"

echo "Running tests..."
pytest

echo "Building Docker image..."
docker build \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    .

echo "Build completed successfully."
"""

print(build_script)


# =============================================================================
# 15. CI/CD DECISION FLOW
# =============================================================================

print("\n" + "=" * 90)
print("15. CI/CD DECISION FLOW")
print("=" * 90)

print("""
SOURCE CHANGE
     |
     v
Pipeline Triggered
     |
     v
Checkout Repository
     |
     v
Install Dependencies
     |
     v
Run Tests
     |
     +------------------+
     |                  |
   Failure            Success
     |                  |
     v                  v
Stop Pipeline       Build Image
                        |
                        v
                  Security / Quality
                        |
                        +------------------+
                        |                  |
                      Failure            Success
                        |                  |
                        v                  v
                    Stop Pipeline     Push Image
                                           |
                                           v
                                   Infrastructure Ready?
                                           |
                                           +---------+
                                           |         |
                                          No        Yes
                                           |         |
                                           v         v
                                     Terraform    Deploy
                                                     |
                                                     v
                                               Kubernetes
                                                     |
                                                     v
                                              Health Checks
""")


# =============================================================================
# 16. DECLARATIVE VS IMPERATIVE OPERATIONS
# =============================================================================

print("\n" + "=" * 90)
print("16. DECLARATIVE VS IMPERATIVE OPERATIONS")
print("=" * 90)

print("""
Imperative approach:

    "Perform these exact steps."

Example:

    1. Create a server.
    2. Install Docker.
    3. Start the application.
    4. Create another server.


Declarative approach:

    "This is the desired final state."

Example:

    replicas = 3


Terraform and Kubernetes strongly emphasize declarative infrastructure and
workload definitions.

Declarative systems generally involve reconciliation:

Current State
       |
       v
Compare
       |
       v
Desired State
       |
       v
Determine Difference
       |
       v
Perform Required Changes
""")


# =============================================================================
# 17. IDEMPOTENCY
# =============================================================================

print("\n" + "=" * 90)
print("17. IDEMPOTENCY IN DEVOPS")
print("=" * 90)

print("""
Idempotency means that repeatedly applying an operation produces the same
intended result after the desired state has been reached.

Example desired state:

    application replicas = 3


First application:

    Current = 0
    Desired = 3
    Action = Create 3


Second application:

    Current = 3
    Desired = 3
    Action = No change


Idempotent infrastructure operations are valuable because automation is often
executed repeatedly.
""")


# =============================================================================
# 18. IMMUTABLE INFRASTRUCTURE
# =============================================================================

print("\n" + "=" * 90)
print("18. IMMUTABLE INFRASTRUCTURE")
print("=" * 90)

print("""
Traditional mutable server:

Server
   |
   +-- Application Version 1
   |
   +-- Manual changes
   |
   +-- More manual changes
   |
   +-- Application Version 2


Immutable infrastructure approach:

Build Version 1 image
        |
        v
Deploy Version 1

Later:

Build Version 2 image
        |
        v
Replace Version 1 with Version 2


Containers naturally support immutable application packaging when image tags,
build processes, and deployment practices are designed appropriately.
""")


# =============================================================================
# 19. DEVOPS SECURITY PRINCIPLES
# =============================================================================

print("\n" + "=" * 90)
print("19. SECURITY CONSIDERATIONS ACROSS THE TOOLCHAIN")
print("=" * 90)

print("""
Git
    - Avoid committing credentials.
    - Protect branches.
    - Review pull requests.
    - Control repository access.

Linux
    - Apply least privilege.
    - Control SSH access.
    - Maintain patches.
    - Review file permissions.

Bash
    - Validate input.
    - Avoid unsafe variable expansion.
    - Protect secrets from logs.

Docker
    - Use trusted images.
    - Minimize image contents.
    - Avoid unnecessary root execution.
    - Scan dependencies and images.

Jenkins and GitHub Actions
    - Protect credentials.
    - Limit workflow permissions.
    - Control third-party plugins and actions.
    - Isolate sensitive workloads.

Terraform
    - Protect state.
    - Restrict cloud credentials.
    - Review infrastructure plans.

Kubernetes
    - Use RBAC.
    - Apply network policies where appropriate.
    - Restrict privileged containers.
    - Manage secrets carefully.
    - Define resource constraints.
""")


# =============================================================================
# 20. FINAL TECHNICAL INTEGRATION
# =============================================================================

print("\n" + "=" * 90)
print("20. DEVOPS ECOSYSTEM AS AN ENGINEERING SYSTEM")
print("=" * 90)

print("""
The DevOps tools ecosystem can be understood as a connected engineering system.

Git manages the history of software and infrastructure definitions.

Linux provides the operating environment used by servers, build agents,
containers, and orchestration platforms.

Bash provides lightweight command-line automation.

Docker packages applications into portable container images.

Jenkins and GitHub Actions automate integration, testing, packaging, and
deployment workflows.

Terraform defines and provisions infrastructure using code.

Kubernetes schedules, operates, scales, and reconciles containerized workloads.

The most important characteristic of this ecosystem is the interaction between
the tools rather than the isolated use of any individual tool.

A practical DevOps workflow therefore depends on understanding how source code,
automation, infrastructure, containers, and orchestration move together through
a controlled and reproducible software delivery process.
""")

print("\n" + "=" * 90)
print("END OF DEVOPS TOOLS ECOSYSTEM LEARNING SCRIPT")
print("=" * 90)

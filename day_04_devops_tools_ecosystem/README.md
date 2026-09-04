# DevOps Tools Ecosystem: Git, Linux, Bash, Docker, Jenkins, GitHub Actions, Terraform, Kubernetes

## Introduction

The DevOps tools ecosystem consists of technologies used to manage the complete lifecycle of software delivery. It connects software development, source control, automation, infrastructure provisioning, application packaging, deployment, and runtime operations.

The technologies covered are:

- Git
- Linux
- Bash
- Docker
- Jenkins
- GitHub Actions
- Terraform
- Kubernetes

These technologies operate at different layers of a software engineering environment. Their individual purposes are important, but their real value becomes visible when they are integrated into a controlled software delivery workflow.

A typical DevOps lifecycle can be represented as:

    Planning
       |
       v
    Development
       |
       v
    Source Control
       |
       v
    Build
       |
       v
    Testing
       |
       v
    Continuous Integration
       |
       v
    Containerization
       |
       v
    Infrastructure Provisioning
       |
       v
    Deployment
       |
       v
    Container Orchestration
       |
       v
    Operations

The purpose of DevOps is not simply to automate individual commands. It is to establish a reliable engineering process in which application code, infrastructure, environments, and deployment procedures can be managed consistently.

---

# 1. Git

## 1.1 What Git Is

Git is a distributed version control system used to track changes in source code and other project files.

Version control provides a historical record of development. Instead of manually maintaining multiple copies of a project, Git allows developers to create commits representing meaningful states of the project.

Git provides:

- Version history
- Branching
- Merging
- Collaboration
- Change tracking
- Rollback
- Distributed repositories
- Integration with CI/CD systems
- Support for code review workflows

Git is distributed because each cloned repository normally contains the project's complete history rather than merely a working copy of the latest files.

---

## 1.2 Git Working Areas

Git can be understood through four major locations:

    Working Directory
           |
           | git add
           v
    Staging Area
           |
           | git commit
           v
    Local Repository
           |
           | git push
           v
    Remote Repository

The working directory contains the files being edited.

The staging area contains changes selected for the next commit.

The local repository contains the project's local history.

The remote repository provides a shared location for collaboration.

---

## 1.3 Important Git Commands

Common commands include:

    git init

Creates a new Git repository.

    git clone <repository>

Creates a local copy of an existing repository.

    git status

Shows the current state of the working tree.

    git add <file>

Places a file's changes into the staging area.

    git commit -m "message"

Creates a commit.

    git log

Displays commit history.

    git diff

Displays differences between versions or working states.

    git branch

Displays or manages branches.

    git switch <branch>

Changes the current branch.

    git switch -c feature/login

Creates and switches to a new branch.

    git merge <branch>

Merges another branch into the current branch.

    git fetch

Downloads information from a remote repository without automatically integrating it.

    git pull

Fetches remote changes and integrates them according to the configured workflow.

    git push

Uploads local commits to a remote repository.

---

## 1.4 Git Commits

A commit represents a recorded point in repository history.

A simplified history looks like:

    A ---- B ---- C ---- D

Each commit contains information about the project state and references its parent history.

Git identifies objects through cryptographic hashes.

For example:

    8f3d1a7c4e8b...

A commit should represent a meaningful logical change rather than an arbitrary collection of unrelated modifications.

---

## 1.5 Git Branches

Branches provide independent development paths.

For example:

    A ---- B ---- C
                \
                 D ---- E
                       ^
                       |
                 feature/login

The main branch and feature branch can evolve independently.

A common workflow is:

    git switch -c feature/login

Developers then commit changes on the feature branch.

When the work is ready, it can be merged into the main development line.

---

## 1.6 Merge

A merge combines histories.

Example:

    A ---- B ---- C -------- M
                \          /
                 D ---- E

The merge commit M combines the two development histories.

Merge is useful when preserving the actual branching history is important.

---

## 1.7 Rebase

Rebase changes the base of a series of commits.

Original:

    A ---- B ---- C
           \
            D ---- E

After rebase:

    A ---- B ---- C ---- D' ---- E'

Rebase can produce a more linear history, but it rewrites commits.

Rewriting commits that have already been shared can create synchronization problems for other developers. For that reason, rebase should be used carefully on shared branches.

---

## 1.8 Merge Conflicts

A merge conflict occurs when Git cannot automatically determine how competing changes should be combined.

A conflict can appear as:

    <<<<<<< HEAD
    port = 8000
    =======
    port = 8080
    >>>>>>> feature/config-update

The developer must determine the correct final version, remove the conflict markers, and stage the resolved file.

Typical commands are:

    git status
    git diff
    git add <file>
    git commit

Conflict resolution is a normal part of collaborative version control.

---

# 2. Linux

## 2.1 Linux in DevOps

Linux is an important operating environment for DevOps engineering.

Linux systems are commonly used for:

- Cloud servers
- Virtual machines
- Container hosts
- CI/CD runners
- Kubernetes nodes
- Application servers
- Database servers
- Network infrastructure

A DevOps engineer therefore needs practical knowledge of the Linux command line, filesystem, permissions, processes, networking, services, environment variables, and logs.

---

## 2.2 Linux Filesystem

Linux uses a hierarchical filesystem.

Important directories include:

    /
    ├── home
    ├── root
    ├── etc
    ├── var
    ├── tmp
    ├── usr
    ├── bin
    ├── sbin
    ├── opt
    ├── proc
    └── dev

Their common purposes are:

| Directory | Purpose |
|---|---|
| `/` | Root of the filesystem |
| `/home` | User home directories |
| `/root` | Root user's home directory |
| `/etc` | System configuration |
| `/var` | Variable data such as logs |
| `/tmp` | Temporary files |
| `/usr` | Programs, libraries and shared resources |
| `/bin` | Essential command binaries |
| `/sbin` | System administration binaries |
| `/opt` | Optional software |
| `/proc` | Virtual filesystem containing process and kernel information |
| `/dev` | Device files |

---

## 2.3 Basic Linux Commands

Common commands include:

    pwd
    ls
    ls -la
    cd
    mkdir
    touch
    cp
    mv
    rm
    cat
    less
    head
    tail
    grep
    find

Examples:

    pwd

Displays the current directory.

    ls -la

Displays files including hidden files with detailed metadata.

    cd /var/log

Changes the current directory.

    mkdir deployment

Creates a directory.

    touch application.log

Creates a file if it does not exist.

    cp source.txt destination.txt

Copies a file.

    mv old.txt new.txt

Moves or renames a file.

    rm file.txt

Removes a file.

---

## 2.4 Pipes and Redirection

Linux commands can be combined.

For example:

    grep ERROR application.log

Searches for lines containing ERROR.

Pipelines pass the output of one command into another:

    cat application.log | grep ERROR

Output can also be redirected:

    command > output.txt

This replaces the output file contents.

Appending can be performed using:

    command >> output.txt

Standard input can be redirected using:

    command < input.txt

Pipelines and redirection form an important part of command-line automation.

---

## 2.5 Linux Permissions

Linux permissions determine what users and groups can do with files.

A representation such as:

    -rwxr-xr--

can be understood as:

    File type | Owner | Group | Others

The permissions are:

    r = read
    w = write
    x = execute

Numeric representation uses:

    read    = 4
    write   = 2
    execute = 1

Therefore:

    7 = rwx
    6 = rw-
    5 = r-x
    4 = r--

For example:

    chmod 755 script.sh

gives:

    Owner  = rwx
    Group  = r-x
    Others = r-x

Another example:

    chmod 600 secret.txt

gives:

    Owner  = rw-
    Group  = ---
    Others = ---

Permissions are particularly important when dealing with deployment scripts, private keys, application files, configuration files, and service accounts.

---

## 2.6 Linux Processes

A process is an executing program.

Useful commands include:

    ps
    ps aux
    top
    htop

A process can be terminated using:

    kill <PID>

A termination request can be sent with:

    kill -TERM <PID>

A forceful termination can be performed with:

    kill -9 <PID>

SIGTERM gives an application an opportunity to shut down gracefully.

SIGKILL forces termination and does not provide the application an opportunity to perform normal cleanup.

Graceful shutdown is important for production applications because applications may need to finish requests, close connections, flush buffers, or release resources.

---

## 2.7 systemd

Many modern Linux distributions use systemd for service management.

Typical commands include:

    systemctl status nginx
    systemctl start nginx
    systemctl stop nginx
    systemctl restart nginx
    systemctl enable nginx
    systemctl disable nginx

A simplified service definition may contain:

    [Unit]
    Description=Example Application

    [Service]
    ExecStart=/usr/bin/python3 /opt/app/main.py
    Restart=always

    [Install]
    WantedBy=multi-user.target

systemd is useful for managing long-running services and controlling their startup behavior.

---

# 3. Bash

## 3.1 Bash as a DevOps Tool

Bash is a command shell and scripting language commonly used in Linux environments.

It is useful for:

- Deployment automation
- Build automation
- File manipulation
- Environment setup
- Server administration
- Log processing
- Health checks
- CI/CD commands

Bash is particularly useful when several Linux commands must be executed in a controlled sequence.

---

## 3.2 Bash Script Structure

A basic script may start with:

    #!/usr/bin/env bash

The shebang tells the operating system which interpreter should execute the script.

A variable can be defined as:

    NAME="DevOps"

The value can be accessed using:

    echo "$NAME"

Bash variables do not use spaces around the assignment operator.

Correct:

    VERSION="1.0"

Incorrect:

    VERSION = "1.0"

---

## 3.3 Environment Variables

A shell variable can be exported:

    export VERSION="1.0"

An exported variable becomes available to child processes.

This is important in DevOps because scripts frequently launch:

- Python programs
- Docker commands
- Terraform
- Kubernetes tools
- Build systems
- Test frameworks

Environment variables are commonly used for configuration.

Examples include:

    DATABASE_HOST
    DATABASE_PORT
    API_URL
    ENVIRONMENT

Sensitive values should be handled through appropriate secret-management mechanisms rather than being embedded directly in source code.

---

## 3.4 Conditions

Bash supports conditional logic.

Example:

    ENVIRONMENT="${1:-development}"

    if [ "$ENVIRONMENT" = "production" ]; then
        echo "Production deployment"
    else
        echo "Non-production deployment"
    fi

This allows scripts to change their behavior based on environment or input.

---

## 3.5 Loops

Bash supports loops.

Example:

    for service in api frontend worker
    do
        echo "Checking $service"
    done

Loops are useful when the same operation needs to be applied to multiple files, servers, services, or configuration values.

---

## 3.6 Exit Codes

Unix commands communicate success or failure through exit codes.

Conventionally:

    0       = success
    non-zero = failure

The previous command's exit status can be inspected with:

    echo $?

CI/CD systems rely heavily on exit codes.

If a test command returns a non-zero exit status, a pipeline can interpret the test stage as failed.

---

## 3.7 Defensive Bash

A commonly used Bash configuration is:

    set -euo pipefail

The options have different purposes.

`-e` causes the script to stop when a command fails under the applicable shell rules.

`-u` treats references to unset variables as errors.

`pipefail` causes a pipeline to reflect a failure from an earlier command rather than reporting success based only on the final command.

Example:

    #!/usr/bin/env bash

    set -euo pipefail

    pytest
    docker build -t application:latest .

This approach makes automation failures more visible.

---

# 4. Docker

## 4.1 Containerization

Docker is a platform for building and running containerized applications.

A container packages an application and the dependencies required for execution into a standardized runtime unit.

Traditional deployment may look like:

    Application
         |
         v
    Server
         |
         v
    Manually installed dependencies
         |
         v
    Operating System

Containerized deployment looks more like:

    Application
         |
         v
    Dependencies
         |
         v
    Container Image
         |
         v
    Container Runtime
         |
         v
    Host Operating System

Containers share the host kernel while providing process and filesystem isolation.

---

## 4.2 Containers and Virtual Machines

A virtual machine generally includes:

    Application
    Dependencies
    Guest Operating System
    Virtualization Layer
    Host Operating System
    Hardware

A container generally uses:

    Application
    Dependencies
    Container Runtime
    Host Operating System
    Hardware

Containers are therefore generally lighter than full virtual machines because they do not require a complete guest operating system for every application instance.

---

## 4.3 Docker Images

A Docker image is a packaged template used to create containers.

For example:

    python:3.12

can be used as the basis for a Python application image.

A running container is an instance created from an image.

The conceptual relationship is:

    Docker Image
         |
         +------ Container 1
         |
         +------ Container 2
         |
         +------ Container 3

Multiple containers can be created from the same image.

---

## 4.4 Dockerfile

A Dockerfile defines how an image is constructed.

Example:

    FROM python:3.12-slim

    WORKDIR /app

    COPY requirements.txt .

    RUN pip install --no-cache-dir -r requirements.txt

    COPY . .

    EXPOSE 8000

    CMD ["python", "main.py"]

Important instructions include:

`FROM`

Selects the base image.

`WORKDIR`

Sets the working directory.

`COPY`

Copies files into the image.

`RUN`

Executes commands while building the image.

`EXPOSE`

Documents an intended container port.

`CMD`

Defines the default command for the container.

---

## 4.5 Docker Build

An image can be built with:

    docker build -t myapp:1.0 .

The `-t` option assigns a name and tag.

The final `.` represents the build context.

---

## 4.6 Docker Containers

Common commands include:

    docker run myapp:1.0

Starts a container.

    docker ps

Lists running containers.

    docker ps -a

Lists running and stopped containers.

    docker logs <container>

Displays container logs.

    docker exec -it <container> sh

Starts an interactive shell inside a running container when the image provides the required shell.

    docker stop <container>

Stops a container.

    docker rm <container>

Removes a container.

---

## 4.7 Docker Port Mapping

Suppose an application listens on port 8000 inside a container.

The container can be exposed on host port 8080:

    docker run -p 8080:8000 myapp

The relationship is:

    Host Port 8080
          |
          v
    Container Port 8000

Port mapping does not change the application's internal listening port.

---

## 4.8 Docker Networking

Docker provides networking mechanisms that allow containers to communicate.

A custom network can be created with:

    docker network create application-network

An architecture might contain:

    frontend
       |
       v
      api
       |
       v
    database

When containers share an appropriate network, applications can communicate through container or service names according to the configured networking environment.

---

## 4.9 Docker Volumes

Container writable storage is not normally suitable for important persistent application data.

Docker volumes provide persistent storage.

Example:

    docker volume create postgres-data

A volume can be mounted:

    docker run \
        -v postgres-data:/var/lib/postgresql/data \
        postgres

The data can remain available even when the original container is removed and recreated.

---

## 4.10 Docker Image Layers

Docker images are built from layers.

A Dockerfile such as:

    FROM python:3.12

    COPY requirements.txt .

    RUN pip install -r requirements.txt

    COPY . .

creates a sequence of filesystem changes.

Layer caching can improve build performance.

If the dependency file has not changed, the dependency installation layer can potentially be reused.

This is why it is generally useful to copy relatively stable dependency definitions before frequently changing application source code.

---

# 5. Jenkins

## 5.1 Jenkins and CI/CD

Jenkins is an automation server used to implement CI/CD pipelines.

A Jenkins pipeline can perform:

- Source checkout
- Dependency installation
- Compilation
- Testing
- Packaging
- Docker image creation
- Security checks
- Deployment
- Notifications
- Cleanup

A typical workflow is:

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

---

## 5.2 Jenkinsfile

A Jenkins pipeline can be represented using a Jenkinsfile.

Example:

    pipeline {
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

This is a declarative Jenkins pipeline.

---

## 5.3 Jenkins Pipeline Structure

A pipeline commonly contains:

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

An `agent` specifies where execution occurs.

`environment` defines environment variables.

`stages` organizes pipeline operations.

`stage` represents a logical phase.

`steps` contain the actual commands.

`post` can define actions that occur after stages complete.

---

## 5.4 Jenkins Agents

Jenkins uses agents to execute jobs.

A conceptual architecture is:

                    Jenkins Controller
                           |
              +------------+------------+
              |            |            |
              v            v            v
           Linux         Docker       Windows
           Agent         Agent        Agent

Different agents can provide different operating systems, tools, dependencies, or hardware.

Jenkins can therefore distribute work according to job requirements.

---

# 6. GitHub Actions

## 6.1 GitHub Actions

GitHub Actions is a workflow automation platform integrated with GitHub repositories.

Workflow definitions are normally stored under:

    .github/workflows/

Workflow files use YAML.

Important concepts are:

- Workflow
- Event
- Job
- Step
- Runner
- Action

---

## 6.2 Workflow

A workflow defines an automation process.

Example:

    name: Python CI

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
            run: pytest

---

## 6.3 Events

A workflow can be triggered by events.

Common events include:

    push
    pull_request
    workflow_dispatch
    schedule

A `push` event can execute a workflow when code is pushed.

A `pull_request` event can execute checks for pull requests.

`workflow_dispatch` can allow manual execution.

`schedule` can execute workflows according to cron schedules.

---

## 6.4 Jobs

A workflow can contain multiple jobs.

Example conceptual structure:

    Workflow
       |
       +-- Build
       |
       +-- Test
       |
       +-- Security Scan
       |
       +-- Package
       |
       +-- Deploy

Jobs can have dependencies.

A deployment job can be configured to execute only after a successful test job.

---

## 6.5 Steps

Steps are individual operations within a job.

For example:

    Checkout source
        ↓
    Install Python
        ↓
    Install dependencies
        ↓
    Run tests

A step can execute a shell command or use a reusable action.

---

## 6.6 Actions

Actions are reusable components.

Example:

    uses: actions/checkout@v4

The checkout action retrieves repository contents for the workflow runner.

Other actions can configure programming languages, cloud credentials, artifact handling, container registries, or other automation requirements.

Third-party actions should be evaluated carefully because workflow actions execute with the permissions granted to the workflow.

---

## 6.7 Secrets

Credentials should not be hardcoded in workflow files.

A workflow can reference a configured secret:

    env:
      API_KEY: ${{ secrets.API_KEY }}

Secrets can be used for:

- API credentials
- Cloud credentials
- Registry authentication
- Signing credentials
- Deployment credentials

Secret exposure remains possible if workflows deliberately print sensitive values or execute untrusted code with excessive permissions. Permissions should therefore be minimized.

---

## 6.8 Matrix Builds

Matrix builds allow the same job to execute across several environments.

Example:

    strategy:
      matrix:
        python-version:
          - "3.10"
          - "3.11"
          - "3.12"

Conceptually:

    Test
      |
      +---- Python 3.10
      |
      +---- Python 3.11
      |
      +---- Python 3.12

This is useful when compatibility across multiple versions must be tested.

---

# 7. Terraform

## 7.1 Infrastructure as Code

Terraform is an Infrastructure as Code tool.

Infrastructure can include:

- Virtual machines
- Networks
- Storage
- Databases
- Load balancers
- DNS
- Cloud resources
- Kubernetes resources

Instead of manually configuring infrastructure through a graphical interface, infrastructure can be described using configuration files.

The workflow is:

    Terraform Configuration
            |
            v
    terraform init
            |
            v
    terraform validate
            |
            v
    terraform plan
            |
            v
    terraform apply
            |
            v
    Infrastructure

---

## 7.2 Declarative Infrastructure

Terraform uses a declarative configuration model.

Instead of specifying every individual operation, the engineer describes the desired infrastructure.

For example:

    Desired:
    3 application servers

Suppose the current infrastructure contains:

    2 application servers

Terraform can determine that one additional server is required.

This can be represented as:

    Current State
          |
          v
    Desired State
          |
          v
    Difference
          |
          v
    Required Changes

---

## 7.3 Terraform Configuration

A basic Terraform configuration may look like:

    terraform {
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

The exact configuration depends on the provider and resources being managed.

---

## 7.4 terraform init

The command:

    terraform init

initializes a Terraform working directory.

It prepares the required providers and modules.

---

## 7.5 terraform fmt

The command:

    terraform fmt

formats Terraform configuration files into a consistent style.

---

## 7.6 terraform validate

The command:

    terraform validate

checks whether the configuration is syntactically and structurally valid according to Terraform's configuration rules.

---

## 7.7 terraform plan

The command:

    terraform plan

calculates and displays the changes Terraform intends to make.

A plan may indicate:

    + create
    ~ update
    - destroy

This allows infrastructure changes to be reviewed before they are applied.

---

## 7.8 terraform apply

The command:

    terraform apply

applies the planned infrastructure changes.

It should be treated as an operational change because it can create, modify, or destroy infrastructure.

---

## 7.9 terraform destroy

The command:

    terraform destroy

requests removal of infrastructure managed by Terraform.

Because infrastructure deletion can be destructive, this command requires careful handling.

---

## 7.10 Terraform State

Terraform maintains state information.

The conceptual relationship is:

    Terraform Configuration
            |
            v
          State
            |
            v
    Actual Infrastructure

State helps Terraform understand which configuration resources correspond to real infrastructure resources.

State can contain sensitive information depending on the resources being managed.

In team environments, state is commonly stored in a remote backend with appropriate access control and mechanisms for coordinating concurrent operations.

---

## 7.11 Terraform Variables

Variables allow reusable configurations.

For example:

    variable "region" {
      type    = string
      default = "ap-south-1"
    }

The configuration can reference:

    var.region

Variables allow the same module or configuration to be used across multiple environments with different inputs.

---

## 7.12 Terraform Outputs

Outputs expose values from a Terraform configuration.

Example:

    output "application_endpoint" {
      value = aws_instance.application.public_ip
    }

Outputs are useful when information generated by infrastructure needs to be consumed by another configuration or displayed after an operation.

---

## 7.13 Terraform Modules

Modules provide reusable infrastructure components.

Example:

    modules/
    ├── network/
    ├── database/
    └── application/

A root configuration can use a module:

    module "network" {
      source = "./modules/network"
    }

Modules support:

- Reusability
- Standardization
- Separation of concerns
- Maintainability
- Consistent infrastructure patterns

---

# 8. Kubernetes

## 8.1 Container Orchestration

Kubernetes is a container orchestration platform.

Running a single container manually is relatively straightforward.

Operating hundreds or thousands of containers introduces additional requirements:

- Scheduling
- Health management
- Scaling
- Networking
- Service discovery
- Rolling deployments
- Failure recovery
- Configuration
- Secret handling
- Resource management

Kubernetes provides abstractions for these requirements.

---

## 8.2 Kubernetes Cluster

A simplified Kubernetes architecture is:

    Kubernetes Cluster
          |
          +----------------+
          |                |
          v                v
    Control Plane       Worker Nodes
                            |
                            v
                           Pods
                            |
                            v
                        Containers

The control plane manages the cluster.

Worker nodes run workloads.

---

## 8.3 Control Plane Components

Important control plane concepts include:

### API Server

The API server is the primary interface through which Kubernetes resources are accessed.

### Scheduler

The scheduler determines where unscheduled Pods should run.

### Controller Manager

Controllers continuously work to maintain desired states.

### etcd

etcd stores Kubernetes cluster state.

These components collectively enable Kubernetes to manage cluster resources.

---

# 9. Pods

## 9.1 Pod Definition

A Pod is the smallest deployable unit in Kubernetes.

A Pod can contain one or more containers.

Example:

    Pod
     |
     +-- Application Container
     |
     +-- Sidecar Container

Containers inside a Pod share the Pod's network namespace and can communicate using localhost.

A Pod should generally be considered replaceable rather than a permanent server.

---

# 10. Kubernetes Deployments

## 10.1 Deployment

A Deployment manages replicated application workloads.

Example:

    apiVersion: apps/v1
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

The desired state is:

    replicas = 3

Kubernetes attempts to maintain this state.

If one Pod fails:

    Pod A -> Running
    Pod B -> Failed
    Pod C -> Running

The controller can create a replacement:

    Pod A -> Running
    Pod B -> Failed
    Pod C -> Running
    Pod D -> Starting

Eventually:

    Pod A -> Running
    Pod C -> Running
    Pod D -> Running

This is an example of reconciliation.

---

# 11. ReplicaSets

A Deployment generally manages ReplicaSets, which in turn maintain the required number of Pods.

The relationship can be viewed as:

    Deployment
         |
         v
    ReplicaSet
         |
         +---- Pod
         +---- Pod
         +---- Pod

ReplicaSets help ensure the desired number of Pod replicas exists.

Deployments provide higher-level functionality for managing application revisions and rollouts.

---

# 12. Kubernetes Services

Pods are replaceable, and their IP addresses can change.

A Service provides a stable network abstraction.

Example:

    Client
       |
       v
    Service
       |
       +---- Pod A
       |
       +---- Pod B
       |
       +---- Pod C

A Service selects Pods according to labels.

Common Service types include:

### ClusterIP

Provides internal cluster connectivity.

### NodePort

Exposes a service through a port on cluster nodes.

### LoadBalancer

Can integrate with external load-balancing infrastructure where supported.

---

# 13. Kubernetes Labels and Selectors

Labels identify resources.

Example:

    labels:
      app: application

A Service can select Pods with:

    selector:
      app: application

This creates an important relationship:

    Pod
      |
      +-- label: app=application
      |
      v
    Service selector
      |
      v
    Pod selected

Labels are fundamental to Kubernetes organization and resource selection.

---

# 14. ConfigMaps

Applications often need configuration that should not be embedded directly into application source code.

Examples include:

    DATABASE_HOST
    DATABASE_PORT
    API_URL
    LOG_LEVEL

A ConfigMap can hold non-sensitive configuration.

Conceptually:

    Application
         |
         +---- ConfigMap
         |
         +---- Runtime Configuration

This allows configuration to be separated from application images.

---

# 15. Kubernetes Secrets

Secrets are designed for sensitive configuration.

Examples include:

- Passwords
- Tokens
- API credentials
- Certificates

Conceptually:

    Application
         |
         v
       Secret
         |
         v
    Sensitive Configuration

A Kubernetes Secret should not be interpreted as automatically making a credential completely secure. Access control, encryption, permissions, secret rotation, and cluster security remain important.

---

# 16. Kubernetes Namespaces

Namespaces provide logical separation within a cluster.

A cluster might contain:

    Cluster
       |
       +---- development
       |
       +---- staging
       |
       +---- production

Each namespace can contain separate workloads and resources.

Namespaces can support:

- Organization
- Access control
- Resource management
- Environment separation

Namespaces alone should not be treated as a complete security boundary for every situation.

---

# 17. Kubernetes Scaling

A Deployment can be manually scaled:

    kubectl scale deployment application --replicas=5

The desired state becomes:

    5 replicas

Kubernetes then works toward maintaining that state.

Autoscaling can use metrics to adjust workload capacity.

A conceptual process is:

    Traffic increases
          |
          v
    Resource usage increases
          |
          v
    Autoscaler evaluates metrics
          |
          v
    Replica count increases
          |
          v
    More Pods

When demand decreases, the configured autoscaling behavior can reduce the number of replicas.

---

# 18. Rolling Updates

Kubernetes Deployments can perform rolling updates.

Suppose the current deployment is:

    Pod A -> Version 1.0
    Pod B -> Version 1.0
    Pod C -> Version 1.0

A new version is deployed:

    Pod A -> Version 1.1
    Pod B -> Version 1.0
    Pod C -> Version 1.0

Then:

    Pod A -> Version 1.1
    Pod B -> Version 1.1
    Pod C -> Version 1.0

Finally:

    Pod A -> Version 1.1
    Pod B -> Version 1.1
    Pod C -> Version 1.1

Deployment parameters such as `maxSurge` and `maxUnavailable` influence how the rollout proceeds.

---

# 19. Desired State and Reconciliation

Kubernetes is fundamentally based around desired state.

For example:

    Desired:
    3 application replicas

The actual cluster may temporarily contain:

    2 healthy replicas

A controller observes the difference:

    Desired = 3
    Current = 2

It then attempts to correct the difference.

This produces a continuous reconciliation loop:

    Observe
       |
       v
    Compare
       |
       v
    Desired State
       |
       v
    Take Action
       |
       v
    Observe Again

This is one of the fundamental ideas behind Kubernetes.

---

# 20. Idempotency

Idempotency is important in infrastructure automation.

An idempotent operation can be repeated without continuously producing unintended additional effects after the desired state has been reached.

Example:

    Desired replicas = 3

Initial state:

    0 replicas

The system creates three replicas.

After reconciliation:

    3 replicas

Repeating the same desired-state operation should preserve:

    3 replicas

rather than producing:

    6 replicas

Terraform and Kubernetes both benefit heavily from desired-state and idempotent operational models.

---

# 21. Immutable Infrastructure

Immutable infrastructure means that infrastructure or application artifacts are treated as replaceable rather than repeatedly modified in place.

A mutable approach may look like:

    Server
       |
       v
    Install Version 1
       |
       v
    Modify Server
       |
       v
    Install Version 2
       |
       v
    Modify Again

An immutable approach looks like:

    Build Version 1
          |
          v
    Deploy Version 1

    Build Version 2
          |
          v
    Deploy Version 2
          |
          v
    Replace Version 1

Docker images work well with immutable application artifacts.

Kubernetes deployments also support replacement-based application updates.

---

# 22. Complete DevOps Toolchain

The technologies can be integrated into a single software delivery pipeline.

A representative workflow is:

    Developer
        |
        v
    Linux
        |
        v
    Bash
        |
        v
    Git
        |
        v
    GitHub
        |
        +----------------------+
        |                      |
        v                      v
    GitHub Actions          Jenkins
        |                      |
        +----------+-----------+
                   |
                   v
              Build + Test
                   |
                   v
             Docker Build
                   |
                   v
           Container Registry
                   |
                   v
              Terraform
                   |
                   v
          Cloud Infrastructure
                   |
                   v
             Kubernetes
                   |
                   v
              Deployment
                   |
                   v
                 Pods
                   |
                   v
               Services
                   |
                   v
                Users

Each tool contributes a specific capability.

| Tool | Primary Role |
|---|---|
| Git | Distributed version control |
| Linux | Operating environment |
| Bash | Shell scripting and automation |
| Docker | Containerization |
| Jenkins | CI/CD automation |
| GitHub Actions | GitHub-integrated workflow automation |
| Terraform | Infrastructure as Code |
| Kubernetes | Container orchestration |

---

# 23. End-to-End Project Structure

A project using this ecosystem may contain:

    project/
    |
    ├── app/
    │   ├── main.py
    │   └── requirements.txt
    |
    ├── tests/
    │   └── test_main.py
    |
    ├── scripts/
    │   ├── build.sh
    │   └── deploy.sh
    |
    ├── infrastructure/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    |
    ├── kubernetes/
    │   ├── deployment.yaml
    │   └── service.yaml
    |
    ├── .github/
    │   └── workflows/
    │       └── ci.yml
    |
    ├── Dockerfile
    ├── Jenkinsfile
    └── README.md

This structure separates application code, tests, shell automation, infrastructure definitions, Kubernetes configuration, Docker configuration, Jenkins configuration, and GitHub Actions workflows.

---

# 24. Example Build Script

A Bash build script may contain:

    #!/usr/bin/env bash

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

This script connects Bash, automated testing, and Docker.

---

# 25. Continuous Integration Flow

A CI pipeline can be represented as:

    Source Change
          |
          v
    Pipeline Trigger
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
          +----------------+
          |                |
       Failure           Success
          |                |
          v                v
    Stop Pipeline      Build Image
                            |
                            v
                       Quality Checks
                            |
                            +------------+
                            |            |
                         Failure       Success
                            |            |
                            v            v
                      Stop Pipeline   Push Image

The central purpose of CI is to identify integration problems as early as possible.

---

# 26. Continuous Delivery and Deployment

After CI succeeds, a delivery pipeline can continue:

    Build
      |
      v
    Test
      |
      v
    Package
      |
      v
    Container Image
      |
      v
    Registry
      |
      v
    Infrastructure
      |
      v
    Kubernetes
      |
      v
    Application

Continuous Delivery means the software is maintained in a state where it can be released through an automated or controlled process.

Continuous Deployment goes further by automatically deploying changes when predefined conditions are satisfied.

---

# 27. Terraform and Kubernetes Together

Terraform and Kubernetes solve different but related problems.

Terraform is primarily used to provision and manage infrastructure.

Kubernetes primarily manages containerized workloads and their runtime behavior.

A layered architecture can therefore be:

    Terraform
       |
       v
    Cloud Infrastructure
       |
       v
    Kubernetes Cluster
       |
       v
    Kubernetes Resources
       |
       v
    Application Pods

Terraform may create or manage infrastructure such as:

- Virtual networks
- Subnets
- Load balancers
- Kubernetes clusters
- Databases
- Storage
- IAM-related resources

Kubernetes can then manage:

- Pods
- Deployments
- Services
- ConfigMaps
- Secrets
- Ingress resources
- Autoscaling
- Application rollouts

---

# 28. Jenkins and GitHub Actions

Jenkins and GitHub Actions can both implement CI/CD workflows.

Jenkins is commonly deployed as a separate automation server and provides a large ecosystem of plugins and integration possibilities.

GitHub Actions is tightly integrated into GitHub repositories and defines workflows alongside repository code.

Both can execute:

- Builds
- Tests
- Docker builds
- Security checks
- Deployment operations
- Infrastructure automation

A team may use either one, both, or another CI/CD system depending on architecture, organizational requirements, existing infrastructure, and operational constraints.

---

# 29. Security Across the DevOps Ecosystem

Security must be considered at every layer.

## Git Security

Important practices include:

- Do not commit credentials.
- Protect important branches.
- Review pull requests.
- Control repository access.
- Use appropriate authentication.
- Review repository history for accidental secret exposure.

## Linux Security

Important areas include:

- User permissions
- File permissions
- SSH access
- Patch management
- Service accounts
- Process isolation
- Firewall configuration
- System logging

## Bash Security

Scripts should:

- Validate inputs.
- Handle failures.
- Avoid accidental secret disclosure.
- Quote variables appropriately.
- Avoid unsafe command construction.

For example, quoting variables is generally safer:

    rm -- "$FILE"

rather than constructing commands from untrusted input without appropriate handling.

## Docker Security

Important considerations include:

- Trusted base images
- Minimal images
- Dependency scanning
- Image scanning
- Avoiding unnecessary privileges
- Appropriate user configuration
- Controlled registry access

## CI/CD Security

Jenkins and GitHub Actions should use:

- Least-privilege credentials
- Protected secrets
- Restricted workflow permissions
- Controlled plugins and actions
- Appropriate runner isolation
- Review of third-party automation components

## Terraform Security

Important considerations include:

- State protection
- Cloud credential security
- Least-privilege permissions
- Plan review
- Provider security
- Module trust
- Controlled state access

## Kubernetes Security

Important areas include:

- RBAC
- Service accounts
- Network policies
- Pod security controls
- Image security
- Secret management
- Resource limits
- Namespace-level organization
- Cluster access controls

---

# 30. DevOps as a Systems Discipline

The tools should not be viewed as unrelated software packages.

Git manages change history.

Linux provides the operating environment.

Bash provides command-line automation.

Docker packages applications and dependencies.

Jenkins and GitHub Actions automate software delivery workflows.

Terraform manages infrastructure as code.

Kubernetes manages containerized workloads.

The relationship can be summarized as:

    Source Code
         |
         v
       Git
         |
         v
    CI Automation
         |
         v
       Docker
         |
         v
    Container Registry
         |
         v
    Infrastructure
         |
         v
    Terraform
         |
         v
    Kubernetes
         |
         v
    Running Application

The important engineering concepts connecting these tools are:

- Version control
- Automation
- Reproducibility
- Declarative configuration
- Desired state
- Idempotency
- Immutable artifacts
- Infrastructure as Code
- Continuous Integration
- Continuous Delivery
- Containerization
- Orchestration
- Access control
- Secure credential management
- Repeatable deployments

A DevOps environment becomes effective when these concepts are implemented as a coherent software delivery and infrastructure management process rather than as isolated commands or technologies.

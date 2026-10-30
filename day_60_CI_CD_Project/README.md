# CI/CD Pipeline: Build, Test, Scan, Package and Dockerize

## Project Scope

This project models a continuous integration and continuous delivery pipeline for an inventory health service.

The pipeline has five ordered stages:

1. **Build** compiles or validates application source code.
2. **Test** executes automated checks against application behavior.
3. **Scan** evaluates source code against configured security rules.
4. **Package** creates a release artifact and records its integrity metadata.
5. **Dockerize** prepares a container build context and can optionally build a Docker image.

Each stage has an explicit outcome. A failed required stage prevents later stages from executing. The implementations record stage results, distinguish failure from skipping, and preserve release metadata.

The sample application exposes an inventory service with `/health` and `/inventory` endpoints. Its inventory logic validates stock identifiers, rejects duplicate entries, and prevents invalid quantities.

## Pipeline Architecture

The pipeline is an ordered workflow rather than a collection of independent commands.

    Source Revision
          |
          v
        BUILD
          |
          v
         TEST
          |
          v
         SCAN
          |
          v
       PACKAGE
          |
          v
       DOCKERIZE
          |
          v
    Release Artifact
          |
          v
      Docker Image

Each stage consumes the result of the preceding stage. A release cannot proceed merely because source compilation succeeds. Tests, security policy, package creation and container preparation are separate conditions.

### Stage responsibilities

| Stage | Input | Operation | Successful output |
|---|---|---|---|
| Build | Application source and tests | Compile or syntax-check source | Validated build output |
| Test | Built or validated application | Execute behavioral tests | Test results |
| Scan | Application source | Apply static security rules | Scan result |
| Package | Validated application | Assemble release files and metadata | Release package |
| Dockerize | Release package | Create container context and Dockerfile | Container build context or image |

The implementations stop on the first failed stage. This avoids packaging or containerizing a revision that has failed an earlier quality gate.

## Build

Build establishes that application source is structurally and syntactically valid for the selected runtime.

The Python implementation compiles the application and test modules with `compileall`. The JavaScript implementation uses Node.js syntax checking for both application and test files. The C++ implementation invokes a C++17 compiler with optimization, strict warnings and warnings treated as errors. The Java implementation uses the Java compiler API with the Java 17 release target.

The build stage is not a substitute for testing. Successful compilation does not prove that an application produces correct results or behaves safely with invalid input.

### Build characteristics

| Language | Build mechanism | Build condition |
|---|---|---|
| Python | `compileall` | Application and tests compile |
| JavaScript | `node --check` | Application and tests pass syntax checks |
| C++17 | `g++` with C++17 and strict warning flags | Compiler exits successfully |
| Java 17 | `JavaCompiler` with `--release 17` | Compiler produces class files |

The C++ implementation uses a native compilation process and creates an executable. The Java implementation creates a class directory that becomes the input to the JAR packaging stage.

## Test

Testing evaluates application behavior independently of source compilation.

The sample inventory service enforces a consistent set of domain rules:

- Stock identifiers must be non-empty and follow the required character rules.
- Quantities must be positive integers.
- Duplicate stock identifiers are rejected.
- Inventory listings have a stable ordering.
- The health endpoint returns an HTTP success response.

The Python implementation uses `unittest`. The JavaScript implementation uses Node.js's built-in test runner and assertions. The C++ implementation executes a compiled self-test mode. The Java implementation executes a dedicated self-test mode in the compiled application.

### Test outcomes

| Outcome | Meaning | Pipeline effect |
|---|---|---|
| Passed | The test assertion succeeded | Counts toward the test pass rate |
| Failed | An assertion or execution failed | Blocks release progression |
| Skipped | A test did not execute | May violate the release policy |

A production test suite should cover unit, integration, contract, regression and end-to-end behavior as appropriate. The sample tests focus on inventory validation and service health behavior.

Testing should use controlled data and isolated dependencies. Tests should not rely on production credentials, live customer records or mutable production resources.

## Security Scan

The Scan stage evaluates source code against security rules before release packaging.

The supplied implementations use deliberately limited static checks to make the pipeline behavior executable without external packages. The checks look for selected risky programming patterns and possible hard-coded credentials.

Examples of configured checks include dynamic code evaluation, selected process-execution mechanisms and embedded credential patterns.

A successful sample scan means only that the configured rules did not identify a violation. It does not establish that the application is vulnerability-free.

### Security scanning distinctions

| Scan category | Purpose | Typical findings |
|---|---|---|
| Static application analysis | Inspect source without executing the application | Unsafe calls, injection risks and insecure coding patterns |
| Dependency analysis | Inspect third-party package versions | Known vulnerable libraries |
| Secret detection | Identify exposed credentials | Tokens, passwords and private keys |
| Container scanning | Inspect image layers and operating-system packages | Vulnerable base packages and image configuration issues |
| Runtime testing | Observe application behavior during execution | Runtime weaknesses and unexpected exposure |

The sample scanners do not download vulnerability databases or inspect operating-system packages. A production release policy should integrate dedicated source, dependency, secret and container scanning systems.

### Security gate behavior

Security findings should carry a severity, rule identifier, affected file and a stable fingerprint. A severity threshold determines which findings block release.

The PostgreSQL implementation uses four severity levels:

| Severity | Interpretation |
|---|---|
| Low | Limited impact or maintenance concern |
| Medium | Requires review and planned remediation |
| High | Blocks release under the default policy |
| Critical | Blocks release under the default policy |

A scan can technically complete while its findings prevent release eligibility. Execution success and policy approval are separate concepts.

## Package

Packaging converts a validated application into a release artifact that can be distributed independently of the development workspace.

The package stage runs only after Build, Test and Scan succeed.

### Python

The Python implementation creates a package directory containing the service source and a JSON manifest. The manifest records the application version, file size and SHA-256 checksum. It also creates a ZIP archive with sorted file names and fixed timestamps to make archive contents reproducible for identical inputs.

### JavaScript

The JavaScript implementation creates a release directory containing the application source and its package metadata. It calculates SHA-256 checksums for the packaged files and records them in a manifest.

The package is a relocatable directory rather than a compressed archive. This avoids introducing an additional archive dependency into the Node.js implementation.

### C++17

The C++ implementation packages the compiled executable, original source and a manifest. Its demonstration-level manifest uses FNV-1a checksums. FNV-1a is a non-cryptographic hash and must not be used to authenticate production release artifacts.

A production C++ release process should use a cryptographic digest such as SHA-256 and a separate signing mechanism.

### Java 17

The Java implementation packages compiled class files into an executable JAR. The JAR manifest identifies `com.acme.HealthService` as the application entry point. A release manifest records the JAR's SHA-256 checksum.

### Artifact integrity

A checksum detects a difference between the recorded and calculated file contents. It does not prove who produced the artifact.

A production release system should consider:

- Cryptographic checksums for artifacts and container images.
- Signed release metadata.
- Immutable artifact storage.
- Restricted write access to release repositories.
- Provenance linking the artifact to a source revision and pipeline run.
- Retention rules for build logs and artifacts.

## Dockerize

Dockerization creates a container build context containing the release files and a Dockerfile.

The Dockerfiles use non-root execution identities and expose the service port. Python and JavaScript use runtime-oriented base images. Java uses a Java 17 runtime image. The C++ implementation uses a multi-stage build: the first stage compiles the source, while the final image contains the resulting executable and a smaller runtime environment.

The build context is created by default. Actual image construction is optional and requires a working Docker executable and daemon.

### Container design decisions

| Concern | Implementation decision |
|---|---|
| Runtime isolation | Run the application in a container |
| Process privilege | Use a non-root runtime identity |
| Network exposure | Expose port 8080 for the sample service |
| Image contents | Copy application files or compiled artifacts |
| C++ compilation | Compile in a builder stage and copy the executable into the runtime stage |
| Docker availability | Require Docker only when image construction is requested |

A production image should also use approved base-image versions or digests, scan image layers, avoid unnecessary packages, and apply a documented image-retention policy.

Containerization does not replace application security scanning. An application can be secure at source level but still use an outdated or vulnerable base image.

## Pipeline Execution and Failure Handling

The scripts create dedicated workspaces and refuse to initialize a non-empty workspace without the corresponding marker file. This prevents accidental use of an unrelated directory.

Each implementation records stage status and stops after a failed required stage.

| Status | Meaning |
|---|---|
| Pending | Stage has not started |
| Running | Stage is executing |
| Succeeded | Stage completed successfully |
| Failed | Stage returned an error or violated a required condition |
| Skipped | Stage was not executed because an earlier stage failed |

The Python, JavaScript and Java implementations write a JSON pipeline report. The C++ implementation writes a corresponding report after successful execution.

Process execution uses argument-based invocation where supported. The C++ standard library does not provide a portable process-spawning API, so its example uses fixed command strings with no interpolated user input.

## Python Implementation

The Python implementation is a sequential pipeline orchestrator using the standard library.

### Main mechanisms

| Mechanism | Application |
|---|---|
| `dataclass` | Stores stage results and pipeline configuration |
| `Enum` | Defines stage states |
| `pathlib` | Manages workspace paths and package contents |
| `subprocess.run` | Executes compilation and test processes without a shell |
| `ast` | Inspects Python syntax trees for selected risky calls |
| `hashlib` | Calculates SHA-256 artifact checksums |
| `zipfile` | Creates a reproducible ZIP release archive |
| `unittest` | Exercises inventory behavior |
| `argparse` | Controls workspace, Docker image construction and image tag |

The `Pipeline` class owns the ordered stage list. Each stage runs through a common execution method, which records timestamps, duration, result state and diagnostic information.

The static scan parses application source into an abstract syntax tree. It inspects function calls rather than relying only on text matching for selected Python operations.

The workspace setup routine refuses to clean arbitrary directories. It removes only managed build directories inside a marked workspace.

### Running

Save the first source file as `ci_cd_pipeline.py`.

Run the default pipeline:

    python ci_cd_pipeline.py

Build a Docker image after the Docker context is created:

    python ci_cd_pipeline.py --docker

Use a separate workspace:

    python ci_cd_pipeline.py --workspace ci_cd_experiment

Specify an image tag:

    python ci_cd_pipeline.py --docker --tag inventory-health-service:1.0.0

Python 3.10 or later is required. The normal pipeline does not require third-party Python packages. Docker is required only when `--docker` is supplied.

## JavaScript Implementation

The JavaScript implementation uses Node.js built-in modules and an event-driven pipeline controller.

### Main mechanisms

| Mechanism | Application |
|---|---|
| `EventEmitter` | Publishes stage lifecycle events |
| `Map` | Stores stage state |
| `Promise` | Coordinates asynchronous process execution |
| `spawn` | Runs compiler, test and Docker commands without a shell |
| `node:test` | Executes automated tests |
| `node:crypto` | Calculates SHA-256 checksums |
| `node:fs/promises` | Manages project and package files |
| `fetch` | Tests the sample HTTP health endpoint |

The `Pipeline` class executes asynchronous stage operations in dependency order. It emits events when a stage begins, succeeds or fails. The event stream allows other Node.js components to observe execution without coupling themselves to individual stage implementations.

The package operation creates a release directory and calculates checksums for its files. The Dockerize stage copies that directory into a separate container context.

### Running

Save the second source file as `ci-cd-pipeline.mjs`.

Run:

    node ci-cd-pipeline.mjs

Build the image:

    node ci-cd-pipeline.mjs --docker

Choose a workspace and image tag:

    node ci-cd-pipeline.mjs --workspace ci_cd_js_workspace --tag inventory-health-service:1.0.0

Node.js 18 or later is required. The implementation does not require npm packages.

## C++17 Implementation

The C++ implementation uses a compiled inventory-validation worker as its case study.

### Main mechanisms

| Mechanism | Application |
|---|---|
| `enum class` | Models stage states |
| `struct` | Stores stage results and configuration |
| `std::filesystem` | Manages source, build and package directories |
| `std::map` | Stores ordered inventory records |
| `std::system` | Invokes fixed compiler, test and Docker commands |
| `std::chrono` | Measures stage execution duration |
| `std::exception` | Reports build and pipeline failures |
| `std::uint64_t` | Calculates demonstration FNV-1a checksums |

The inventory worker validates identifiers and quantities, rejects duplicates and provides a self-test mode. The pipeline compiles it with C++17, optimization and strict compiler warnings.

The Scan stage evaluates selected source patterns. The Package stage collects the executable and source. The Dockerfile performs compilation in a builder image and copies the executable into a separate runtime image.

The implementation uses `std::system` because portable process execution is not available in the C++17 standard library. Its commands are fixed rather than constructed from untrusted external input.

### Running

Save the third source file as `ci_cd_pipeline.cpp`.

Compile on Linux:

    g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic ci_cd_pipeline.cpp -o ci_cd_pipeline

Run:

    ./ci_cd_pipeline

Build the container image:

    ./ci_cd_pipeline --docker

On Windows with a suitable C++17 compiler:

    g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic ci_cd_pipeline.cpp -o ci_cd_pipeline.exe

    .\ci_cd_pipeline.exe

The compiler must be accessible through the system path. Docker is needed only for the optional image build.

## Java 17 Implementation

The Java implementation models an enterprise-oriented application release process.

### Main mechanisms

| Mechanism | Application |
|---|---|
| `enum` | Defines pipeline stages and statuses |
| `record` | Represents immutable stage results |
| `EnumMap` | Maintains state for each pipeline stage |
| Functional interface | Represents executable stage actions |
| `JavaCompiler` | Compiles the service against Java 17 |
| `ProcessBuilder` | Executes application tests and Docker operations |
| `JarOutputStream` | Builds the executable JAR |
| `Manifest` | Declares the application entry point |
| `MessageDigest` | Calculates SHA-256 checksums |
| `Files.walk` | Collects compiled class files for packaging |

The Java implementation uses explicit stage actions and a common execution method. The method records timing, changes stage state and captures failures.

The test stage executes the compiled inventory service in self-test mode. The package stage collects the compiled classes into a JAR and writes a release manifest. The Dockerize stage prepares a Java runtime image context and optionally invokes Docker.

A JDK is required because the implementation uses `ToolProvider.getSystemJavaCompiler()` at runtime.

### Running

Save the fourth source file as `CiCdPipelineDemo.java`.

Compile:

    javac --release 17 CiCdPipelineDemo.java

Run:

    java CiCdPipelineDemo

Build the Docker image:

    java CiCdPipelineDemo --docker

Use a separate workspace:

    java CiCdPipelineDemo --workspace ci_cd_java_workspace

Java 17 or later is required.

## PostgreSQL Data Model

The PostgreSQL implementation stores pipeline definitions, runs, stage executions, test results, security findings, artifacts, Docker images and release policies in the `cicd` schema.

### Entity relationships

    pipeline_definitions
            |
            +------ pipeline_policies
            |
            +------ stage_definitions
                        |
                        |
                pipeline_runs
                        |
                        v
                stage_executions
                   /    |    \
                  /     |     \
                 v      v      v
           test_results  security_findings
                        |
                        +------ build_artifacts
                        |
                        +------ docker_images

The model separates pipeline configuration from individual executions. A pipeline definition can have multiple runs, and each run has one execution record for each configured stage.

### Tables

| Table | Responsibility |
|---|---|
| `pipeline_definitions` | Identifies an application pipeline |
| `stage_definitions` | Defines ordered stages and their requirements |
| `pipeline_policies` | Stores release quality and security thresholds |
| `pipeline_runs` | Records source revision, branch, trigger identity and overall state |
| `stage_executions` | Tracks stage state, attempts, timestamps and exit codes |
| `test_results` | Stores individual automated test outcomes |
| `security_findings` | Stores rule identifiers, severity and affected source locations |
| `build_artifacts` | Stores release artifact metadata and checksums |
| `docker_images` | Stores image tags, digests, base images and privilege metadata |

### Database enforcement

The schema uses primary keys, foreign keys, uniqueness constraints, check constraints and indexes.

The `enforce_stage_transition` trigger permits only defined stage transitions. A stage cannot start until all preceding required stages have succeeded.

The `synchronize_run_status` trigger updates the overall pipeline run when a stage starts, fails or completes the final required stage.

Other triggers prevent test results from being attached to non-test stages, findings from being attached to non-scan stages, artifacts from being registered before a successful package stage, and Docker image metadata from being inserted before successful Dockerization.

### Release evaluation

The `evaluate_run` function checks whether a pipeline run satisfies its release policy.

It considers:

- Completion of all required stages.
- Successful test execution and recorded test outcomes.
- Minimum test pass rate.
- Blocking security findings.
- Required release artifacts.
- Required Docker image metadata.

The function returns an eligibility value and a list of blockers. Its result is separate from the execution status of the run.

The two sample runs demonstrate different outcomes. One completes every stage and satisfies the default policy. The other passes Build and Test but fails the Scan stage after a high-severity finding. Its package and Dockerize stages remain pending.

### Database execution

Save the fifth source file as `cicd_pipeline.sql`.

Execute it with PostgreSQL:

    psql -d your_database -f cicd_pipeline.sql

The script recreates the `cicd` schema, creates the database objects, inserts the sample pipeline and runs, demonstrates a rejected stage-order transition, and executes reporting and eligibility queries.

The script uses a transaction so that the schema and sample data are committed together. It is intended for a dedicated learning database because it drops and recreates the `cicd` schema.

## Cross-Language Design Comparison

| Engineering concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Pipeline control | Sequential class | Asynchronous event emitter | Stage execution methods | Explicit stage actions | Run and stage records |
| Build | Bytecode compilation | Syntax validation | Native compilation | Class compilation | Not applicable |
| Test | `unittest` | `node:test` | Executable self-tests | Application self-tests | Test-result storage |
| Scan | AST and text rules | Source policy rules | Source policy rules | Source policy rules | Severity-based release evaluation |
| Package | ZIP and manifest | Release directory | Executable and source | Executable JAR | Artifact metadata |
| Dockerize | Docker context | Docker context | Multi-stage Dockerfile | Java runtime Dockerfile | Image metadata |
| Integrity | SHA-256 | SHA-256 | FNV-1a demonstration hash | SHA-256 | SHA-256 metadata validation |
| Failure behavior | Stop and report | Emit failure and stop | Stop and report | Stop and report | State constraints and triggers |

## Operational Limitations and Production Considerations

The four application implementations use small demonstration projects and focused quality checks. They are complete executable examples of the pipeline sequence, not replacements for a production CI/CD platform.

The following distinctions matter when adapting the design to a real repository:

| Area | Demonstration behavior | Production consideration |
|---|---|---|
| Build environment | Uses locally installed compilers and runtimes | Use controlled, versioned build agents |
| Test coverage | Tests selected business rules | Add integration, regression and end-to-end suites |
| Security scanning | Applies a limited set of source rules | Add SAST, dependency, secret and image scanning |
| Artifact integrity | Records file checksums | Add signing and provenance verification |
| Package storage | Uses a local release directory or archive | Store immutable artifacts in a controlled registry |
| Docker base images | Uses named base-image versions | Pin approved digests and monitor image vulnerabilities |
| Pipeline isolation | Uses a dedicated local workspace | Use isolated, disposable build environments |
| Credentials | No deployment credentials are required | Use short-lived credentials and a secrets manager |
| Retry behavior | Stops after required-stage failure | Define bounded retries for transient failures |
| Release policy | Uses fixed sample policies | Version, review and audit quality gates |

A production pipeline should also preserve the source commit identifier, build environment, toolchain versions, dependency lockfiles, test reports, scan reports, artifact digest and resulting container image digest. This creates a traceable relationship between a source revision and its release outputs.

## Expected Outputs

The default runs create separate workspace directories:

| Implementation | Default workspace | Principal outputs |
|---|---|---|
| Python | `ci_cd_python_workspace` | ZIP archive, manifest, Docker context, pipeline report |
| JavaScript | `ci_cd_js_workspace` | Release directory, checksums, Docker context, pipeline report |
| C++17 | `ci_cd_cpp_workspace` | Native executable, source package, manifest, Dockerfile, pipeline report |
| Java 17 | `ci_cd_java_workspace` | Compiled classes, executable JAR, release manifest, Dockerfile, pipeline report |

The Docker image is built only when the corresponding command-line option is supplied. A generated Dockerfile and build context do not imply that an image has already been built.

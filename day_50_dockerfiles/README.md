# Dockerfiles: FROM, RUN, COPY, CMD, ENTRYPOINT, ENV

## Scope

A Dockerfile is a declarative build recipe for constructing a container image. The instructions in this project focus on six core mechanisms:

| Instruction | Primary role | Phase |
|---|---|---|
| `FROM` | Selects the base image and starts a build stage | Image construction |
| `RUN` | Executes commands during image construction | Image construction |
| `COPY` | Transfers files from the build context into the image | Image construction |
| `ENV` | Defines environment variables persisted as image configuration | Build/runtime configuration |
| `ENTRYPOINT` | Defines the primary executable for the container | Container startup |
| `CMD` | Defines a default command or default arguments | Container startup |

These instructions are related but have different responsibilities. `FROM`, `RUN`, and `COPY` primarily determine image contents. `ENV` establishes configuration. `ENTRYPOINT` and `CMD` determine how a resulting image behaves when a container starts.

## Dockerfile Processing Model

A simplified workflow is:

Build context
→ `FROM`
→ `RUN` / `COPY`
→ image filesystem and metadata
→ container creation
→ `ENTRYPOINT` + `CMD`
→ running process

The distinction between build time and runtime is essential.

`RUN` executes while the image is being built. Its resulting filesystem changes become part of the image.

`CMD` and `ENTRYPOINT` do not execute merely because the Dockerfile is being built. They describe container startup behavior.

## `FROM`

`FROM` establishes the starting filesystem and metadata for a build stage.

Example:

`FROM python:3.13-slim`

The Python implementation parses `FROM` and verifies that it occurs first in the simplified single-stage model. The C++ and Java implementations use typed instruction models to represent it explicitly. The SQL model associates a `FROM` instruction with a registered base image.

A base-image reference can use a tag such as `python:3.13-slim`, but controlled production environments may prefer immutable digest references because tags can move.

The SQL schema records:

- repository name
- tag
- digest
- architecture
- trust status

This allows image governance to be represented as data rather than relying exclusively on textual Dockerfile inspection.

## `RUN`

`RUN` executes a command during image construction.

Example:

`RUN pip install --no-cache-dir -r requirements.txt`

A `RUN` command can install packages, compile software, create directories, modify permissions, or perform other build-time operations.

The important distinction is that the resulting filesystem state belongs to the image. It is not the same as executing a command interactively inside an already-running container.

The implementations model `RUN` as a build operation and as a source of image-layer changes.

The C++ implementation creates a simplified layer plan. Its cache identity incorporates the preceding layer and instruction text. Real Docker build caching is more sophisticated, but the model demonstrates an important engineering principle: changing an earlier build operation can invalidate dependent work.

A practical Dockerfile therefore benefits from deliberate instruction ordering.

For example:

`COPY requirements.txt .`

followed by:

`RUN pip install --no-cache-dir -r requirements.txt`

and only later:

`COPY app.py .`

can allow dependency installation to remain reusable when application source files change but the dependency file does not.

## `COPY`

`COPY` transfers files from the build context into the image.

Example:

`COPY app.py .`

The build context is an important security boundary. A Docker build should not be treated as though arbitrary files from the host filesystem are automatically available to `COPY`.

The Python, JavaScript, C++, and Java implementations reject or model attempts to escape the intended context with paths such as `../`.

A small build context also reduces accidental exposure of credentials, private files, generated artifacts, and unrelated source material.

The SQL implementation records each `COPY` operation and can report its frequency by repository and Dockerfile.

## `ENV`

`ENV` defines environment variables associated with the image.

Example:

`ENV APP_ENV=production`

The value can be available to subsequent build instructions and to containers created from the image.

`ENV` is configuration, not a secure secret store.

The implementations deliberately reject obvious credential patterns such as password, secret, token, or private-key assignments in Dockerfile configuration. This is a policy-oriented check rather than a complete secret detector.

Credentials should not be committed into a Dockerfile or persisted into an image merely because an environment variable is convenient.

The SQL trigger enforces a corresponding database-level validation rule for stored Dockerfile instructions.

## `ENTRYPOINT`

`ENTRYPOINT` identifies the primary executable for a container.

Example:

`ENTRYPOINT ["python", "app.py"]`

It is useful when the image represents a defined executable rather than a general-purpose shell environment.

The exec-form representation is especially useful for predictable process handling because the configured executable can become the container's primary process rather than being unnecessarily wrapped by a shell.

The Python, JavaScript, C++, and Java implementations distinguish `ENTRYPOINT` from `CMD` instead of treating both as generic startup strings.

## `CMD`

`CMD` supplies default startup behavior.

Example:

`CMD ["--port", "8000"]`

When paired with:

`ENTRYPOINT ["python", "app.py"]`

the conceptual startup configuration becomes:

`python app.py --port 8000`

This pairing separates the fixed executable from replaceable default arguments.

A Dockerfile containing only `CMD` can instead define a default command that can normally be replaced by an explicit runtime command.

The distinction is therefore:

| Mechanism | Main responsibility |
|---|---|
| `ENTRYPOINT` | Defines the primary executable |
| `CMD` | Defines defaults for command execution or arguments |

They are complementary rather than interchangeable.

## Python Implementation

The Python program implements a Dockerfile parser and validation model using standard-library facilities.

`DockerInstruction` represents an instruction with:

- instruction keyword
- argument string
- source line number

`DockerfileModel` stores the parsed instructions and provides instruction-specific lookup.

The parser handles:

- blank lines
- comments
- line continuations
- supported instruction validation
- missing arguments
- ordering checks
- environment validation

The script then performs production-oriented checks for startup configuration and obvious secret exposure.

It also demonstrates build-context validation by checking whether a candidate path resolves inside the permitted context.

The Python design uses dictionaries, lists, sets, exceptions, `pathlib`, temporary directories, and standard-library parsing facilities without external dependencies.

## JavaScript Implementation

The JavaScript implementation uses Node.js capabilities to provide an event-driven policy model.

`BuildPolicy` extends `EventEmitter`. Each policy result emits a `rule` event, allowing the policy engine to report decisions as they are evaluated.

`DockerBuildSimulator` asynchronously processes instructions and constructs a simplified representation of image state.

This deliberately differs from the Python implementation. Instead of concentrating on filesystem-oriented parsing and validation, the JavaScript version emphasizes:

- event-driven policy evaluation
- asynchronous processing
- simulated build state
- environment extraction
- startup configuration
- policy result events

No npm dependency is required.

## C++ Implementation

The C++17 program models a Dockerfile as a strongly structured build artifact.

`Dockerfile` owns parsing and structural validation.

`BuildPlanner` converts relevant instructions into a simplified layer plan. `FROM`, `RUN`, and `COPY` are treated as layer-producing operations in the educational model.

`StartupPolicy` evaluates whether the image has a usable `CMD`, `ENTRYPOINT`, or combination.

The implementation uses:

- `std::vector`
- `std::set`
- `std::optional`
- string parsing
- exception-based validation
- immutable-style read access
- explicit domain classes

The layer model demonstrates why instruction order affects cache reuse. A modification to an earlier operation can change the state from which later operations are built.

## Java Implementation

The Java 17 program represents Dockerfile governance as an enterprise-style domain model.

`InstructionType` is an enum representing supported Dockerfile directives.

`Instruction` is an immutable record containing the instruction type, arguments, and source line.

`SecurityPolicy` evaluates repository-level rules such as:

- startup configuration
- credential exposure
- build-context boundaries

`MergeLikePolicyEngine` collects and reports policy decisions.

`ImagePlan` represents build layers separately from policy evaluation.

This separation is important in larger systems. Parsing, security policy, and build planning are different responsibilities and should not be forced into a single class.

The program also models policy results explicitly rather than representing every validation outcome as a boolean with no explanation.

## PostgreSQL Model

The SQL implementation treats Dockerfile processing as relational data.

The main entities are:

| Table | Purpose |
|---|---|
| `repositories` | Stores repository ownership and production status |
| `dockerfiles` | Stores Dockerfile versions and locations |
| `base_images` | Records image repositories, tags, digests, architectures, and trust |
| `instructions` | Stores individual Dockerfile instructions |
| `builds` | Tracks image-build execution states |
| `build_policies` | Defines governance rules |
| `build_policy_results` | Stores policy evaluation results |

The `instructions` table uses a check constraint to restrict stored instruction types.

The trigger `dockerfile_instruction_validation` enforces rules that should not depend solely on application code.

It checks:

- non-empty instruction arguments
- build-context traversal attempts
- obvious credential assignments
- explicit base-image references
- first-instruction ordering

The `evaluate_build` function evaluates a stored Dockerfile against operational policies and returns policy-specific results.

The views provide reporting for instruction composition and build governance.

A transaction demonstrates how a build can move from `RUNNING` to either `PASSED` or `BLOCKED` depending on high-severity policy failures.

## Build Context and Security

A Dockerfile does not operate in isolation. The build context is part of the security boundary.

Files accidentally included in the context can become available to build instructions and may be copied into an image.

Common risks include:

- credentials accidentally included in the build context
- private configuration files copied into images
- unnecessary source material increasing image size
- package installation commands introducing untrusted dependencies
- secrets persisted through `ENV`
- credentials embedded directly into `RUN`
- excessive privileges during image construction
- unnecessarily large base images

A `.dockerignore` file is commonly used to reduce the build context, although it is outside the six instructions modeled here.

## Layering and Cache Behavior

Docker image construction is layer-oriented.

A simplified dependency chain is:

`FROM`
→ `COPY requirements.txt`
→ `RUN install dependencies`
→ `COPY application`
→ runtime metadata

If application source changes after dependency installation, the earlier dependency layer may remain reusable.

If the dependency manifest changes, the installation layer normally requires rebuilding.

This makes instruction ordering a performance concern, not merely a formatting preference.

The implementations intentionally model this relationship without claiming to reproduce Docker's complete builder cache algorithm.

## Failure Conditions

The implementations treat several conditions as failures:

- missing `FROM`
- `FROM` in the wrong position
- unsupported instructions
- empty instruction arguments
- incomplete line continuations
- build-context traversal attempts
- obvious credentials embedded in configuration
- missing startup configuration
- invalid Dockerfile structure

Real Docker builds have additional validation rules and runtime interactions. The examples are focused on the six specified instructions and their relationships.

## Production Considerations

A production Dockerfile should be designed around both reproducibility and minimal attack surface.

Relevant considerations include:

- use controlled base-image references
- minimize unnecessary packages
- keep build contexts small
- avoid credentials in image layers
- separate build-time and runtime configuration
- order expensive or stable build operations to improve caching
- use `ENTRYPOINT` and `CMD` deliberately
- consider non-root execution with `USER`
- inspect dependency provenance
- keep runtime images smaller when practical
- validate images before deployment

`ENV` should be treated as configuration, not as a mechanism for protecting secrets.

`RUN` should contain only the build operations actually required.

`COPY` should transfer only the files required by the resulting image.

## Conceptual Distinction

The six instructions can be viewed through their responsibilities:

| Question | Instruction |
|---|---|
| What image do I start from? | `FROM` |
| What must happen while building? | `RUN` |
| Which files enter the image? | `COPY` |
| Which configuration variables exist? | `ENV` |
| Which executable should start? | `ENTRYPOINT` |
| What default command or arguments should be supplied? | `CMD` |

The most important boundary is between **image construction** and **container execution**.

`FROM`, `RUN`, and `COPY` primarily shape the image.

`ENV` establishes configuration that can affect both construction and execution.

`ENTRYPOINT` and `CMD` define container startup behavior.

Understanding these boundaries prevents common mistakes such as expecting `RUN` to execute when a container starts or treating `ENV` as a secure storage mechanism for credentials.

## Executable Artifacts

The five implementations intentionally use different perspectives:

| File | Perspective |
|---|---|
| Python | Dockerfile parsing, validation, filesystem-aware build-context checks |
| JavaScript | Event-driven policy evaluation and asynchronous build simulation |
| C++17 | Typed build planning, layer modeling, and startup-policy evaluation |
| Java 17 | Enterprise domain modeling and explicit security governance |
| PostgreSQL | Persistent Dockerfile metadata, policy enforcement, workflow state, and reporting |

The shared subject is the Dockerfile lifecycle, while each implementation emphasizes a different engineering concern rather than reproducing the same program in another language.

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

/*
 * Docker CLI case study: operational control for a small service deployment.
 *
 * Compile:
 *   g++ -std=c++17 -Wall -Wextra -pedantic docker_cli.cpp -o docker_cli
 *
 * This program models deployment decisions and can optionally invoke Docker.
 * Use --execute to run actual CLI commands on the local Docker engine.
 */

enum class ContainerState {
    Created,
    Running,
    Stopped,
    Removed,
    Failed
};

std::string stateName(ContainerState state) {
    switch (state) {
        case ContainerState::Created: return "created";
        case ContainerState::Running: return "running";
        case ContainerState::Stopped: return "stopped";
        case ContainerState::Removed: return "removed";
        case ContainerState::Failed: return "failed";
    }
    throw std::logic_error("Unknown container state");
}

struct ContainerSpec {
    std::string name;
    std::string image;
    std::vector<std::string> command;
    ContainerState state = ContainerState::Created;
    int restartCount = 0;
    std::vector<std::string> events;
};

class DeploymentRegistry {
private:
    std::map<std::string, ContainerSpec> containers;

    ContainerSpec& find(const std::string& name) {
        auto it = containers.find(name);
        if (it == containers.end()) {
            throw std::out_of_range("Unknown container: " + name);
        }
        return it->second;
    }

public:
    void registerContainer(ContainerSpec spec) {
        if (spec.name.empty() || spec.image.empty()) {
            throw std::invalid_argument("Container name and image are required");
        }
        if (containers.count(spec.name)) {
            throw std::invalid_argument("Duplicate container name: " + spec.name);
        }
        spec.events.push_back("registered");
        containers.emplace(spec.name, std::move(spec));
    }

    void start(const std::string& name) {
        auto& container = find(name);
        if (container.state == ContainerState::Removed) {
            throw std::logic_error("A removed container cannot be started");
        }
        if (container.state == ContainerState::Running) {
            throw std::logic_error("Container is already running");
        }

        if (container.state == ContainerState::Stopped) {
            ++container.restartCount;
        }

        container.state = ContainerState::Running;
        container.events.push_back("started");
    }

    void stop(const std::string& name) {
        auto& container = find(name);
        if (container.state != ContainerState::Running) {
            throw std::logic_error("Only running containers can be stopped");
        }

        container.state = ContainerState::Stopped;
        container.events.push_back("stopped");
    }

    void remove(const std::string& name) {
        auto& container = find(name);
        if (container.state == ContainerState::Running) {
            throw std::logic_error("Stop the container before registry removal");
        }

        container.state = ContainerState::Removed;
        container.events.push_back("removed");
    }

    void show() const {
        std::cout << "\nDeployment registry\n";
        std::cout << std::left
                  << std::setw(24) << "NAME"
                  << std::setw(18) << "IMAGE"
                  << std::setw(12) << "STATE"
                  << "RESTARTS\n";

        for (const auto& [name, container] : containers) {
            std::cout << std::setw(24) << name
                      << std::setw(18) << container.image
                      << std::setw(12) << stateName(container.state)
                      << container.restartCount << '\n';
        }
    }
};

std::string quoteArgument(const std::string& argument) {
    // POSIX single-quote escaping. This execution helper is intended for
    // POSIX shells and is not a Windows command-line quoting implementation.
    std::string escaped = "'";
    for (char c : argument) {
        if (c == '\'') {
            escaped += "'\\''";
        } else {
            escaped += c;
        }
    }
    escaped += "'";
    return escaped;
}

int executeDocker(const std::vector<std::string>& arguments) {
    if (arguments.empty()) {
        throw std::invalid_argument("Docker argument list cannot be empty");
    }

    std::ostringstream command;
    command << "docker";
    for (const auto& argument : arguments) {
        command << ' ' << quoteArgument(argument);
    }

    std::cout << "$ " << command.str() << '\n';
    return std::system(command.str().c_str());
}

int main(int argc, char* argv[]) {
    bool execute = false;
    if (argc > 2) {
        std::cerr << "Usage: docker_cli [--execute]\n";
        return 2;
    }
    if (argc == 2) {
        if (std::string(argv[1]) != "--execute") {
            std::cerr << "Unknown argument: " << argv[1] << '\n';
            return 2;
        }
        execute = true;
    }

    try {
        DeploymentRegistry registry;

        registry.registerContainer({
            "orders-api",
            "alpine:3.22",
            {"sh", "-c", "while true; do echo orders-ready; sleep 5; done"}
        });

        registry.registerContainer({
            "report-worker",
            "alpine:3.22",
            {"sh", "-c", "echo report-generated"}
        });

        registry.start("orders-api");
        registry.start("report-worker");
        registry.stop("report-worker");
        registry.start("report-worker");
        registry.stop("report-worker");
        registry.show();

        if (!execute) {
            std::cout
                << "\nSimulation only. Pass --execute to issue Docker commands.\n"
                << "The live demonstration uses a uniquely named training container.\n";
            return 0;
        }

        const std::string name = "cpp-docker-cli-case-study";

        // Pull downloads image layers into the local image store. It does not
        // create a running container.
        if (executeDocker({"pull", "alpine:3.22"}) != 0) {
            throw std::runtime_error("Image pull failed");
        }

        // The detached container provides a stable target for ps, exec, logs,
        // stop, and start. The label helps identify the training workload.
        if (executeDocker({
                "run", "-d",
                "--name", name,
                "--label", "purpose=cpp-cli-case-study",
                "alpine:3.22",
                "sh", "-c",
                "while true; do echo orders-ready; sleep 5; done"
            }) != 0) {
            throw std::runtime_error("Container creation failed");
        }

        try {
            if (executeDocker({"ps", "-a"}) != 0)
                throw std::runtime_error("Container listing failed");

            if (executeDocker({"exec", name, "sh", "-c", "echo readiness-check"}) != 0)
                throw std::runtime_error("Exec failed");

            if (executeDocker({"logs", "--tail", "10", name}) != 0)
                throw std::runtime_error("Log retrieval failed");

            if (executeDocker({"stop", "--time", "10", name}) != 0)
                throw std::runtime_error("Stop failed");

            if (executeDocker({"start", name}) != 0)
                throw std::runtime_error("Start failed");

            if (executeDocker({"ps", "-a"}) != 0)
                throw std::runtime_error("Final container listing failed");
        } catch (...) {
            // Cleanup is restricted to the explicitly named container.
            executeDocker({"rm", "-f", name});
            throw;
        }

        if (executeDocker({"rm", "-f", name}) != 0) {
            throw std::runtime_error("Cleanup failed");
        }

    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class CredentialType {
    SecretText,
    UsernamePassword,
    SSHPrivateKey,
    SecretFile,
    Certificate
};

enum class CredentialScope {
    Global,
    System
};

enum class CredentialStatus {
    Active,
    Expired,
    Revoked
};

string toString(CredentialType type) {
    switch (type) {
        case CredentialType::SecretText: return "SECRET_TEXT";
        case CredentialType::UsernamePassword: return "USERNAME_PASSWORD";
        case CredentialType::SSHPrivateKey: return "SSH_PRIVATE_KEY";
        case CredentialType::SecretFile: return "SECRET_FILE";
        case CredentialType::Certificate: return "CERTIFICATE";
    }
    throw runtime_error("Unknown credential type");
}

string toString(CredentialScope scope) {
    return scope == CredentialScope::Global ? "GLOBAL" : "SYSTEM";
}

string toString(CredentialStatus status) {
    switch (status) {
        case CredentialStatus::Active: return "ACTIVE";
        case CredentialStatus::Expired: return "EXPIRED";
        case CredentialStatus::Revoked: return "REVOKED";
    }
    throw runtime_error("Unknown credential status");
}

class SecurityException : public runtime_error {
public:
    explicit SecurityException(const string& message)
        : runtime_error(message) {}
};

class ValidationException : public runtime_error {
public:
    explicit ValidationException(const string& message)
        : runtime_error(message) {}
};

class NotFoundException : public runtime_error {
public:
    explicit NotFoundException(const string& message)
        : runtime_error(message) {}
};

struct SecretMaterial {
    string username;
    string value;
    bool usesUsername = false;
};

struct Credential {
    string id;
    string description;
    string owner;
    CredentialType type;
    CredentialScope scope;
    CredentialStatus status = CredentialStatus::Active;
    int version = 1;
    chrono::system_clock::time_point expiresAt;
    bool hasExpiration = false;
};

struct AuditEvent {
    string action;
    string credentialId;
    string actor;
    string outcome;
    string details;
};

class CredentialStore {
private:
    map<string, Credential> metadata;
    map<string, SecretMaterial> secretVault;
    vector<AuditEvent> audit;

    static bool validId(const string& id) {
        static const regex pattern(
            "^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$"
        );
        return regex_match(id, pattern);
    }

    void record(
        const string& action,
        const string& id,
        const string& actor,
        const string& outcome,
        const string& details = ""
    ) {
        audit.push_back({
            action, id, actor, outcome, details
        });
    }

    bool isValid(const Credential& credential) const {
        if (credential.status != CredentialStatus::Active) {
            return false;
        }

        if (
            credential.hasExpiration &&
            chrono::system_clock::now() >= credential.expiresAt
        ) {
            return false;
        }

        return true;
    }

public:
    void add(
        const string& id,
        const string& description,
        const string& owner,
        CredentialType type,
        CredentialScope scope,
        SecretMaterial secret,
        int validityDays = 0
    ) {
        if (!validId(id)) {
            throw ValidationException("Invalid credential ID");
        }

        if (metadata.count(id)) {
            throw ValidationException("Duplicate credential ID");
        }

        if (description.empty() || owner.empty()) {
            throw ValidationException("Description and owner are required");
        }

        if (secret.value.empty()) {
            throw ValidationException("Secret cannot be empty");
        }

        if (
            type == CredentialType::UsernamePassword &&
            (!secret.usesUsername || secret.username.empty())
        ) {
            throw ValidationException("Username is required");
        }

        Credential credential{
            id,
            description,
            owner,
            type,
            scope
        };

        if (validityDays > 0) {
            credential.hasExpiration = true;
            credential.expiresAt =
                chrono::system_clock::now() +
                chrono::hours(24 * validityDays);
        }

        metadata.emplace(id, credential);
        secretVault.emplace(id, secret);

        record("CREATE", id, owner, "SUCCESS");
    }

    const Credential& getMetadata(const string& id) const {
        auto iterator = metadata.find(id);

        if (iterator == metadata.end()) {
            throw NotFoundException("Credential not found: " + id);
        }

        return iterator->second;
    }

    const SecretMaterial& resolve(
        const string& id,
        const string& pipeline,
        const string& actor,
        CredentialType requiredType,
        bool allowSystem = false
    ) {
        auto iterator = metadata.find(id);

        if (iterator == metadata.end()) {
            throw NotFoundException("Credential not found");
        }

        Credential& credential = iterator->second;

        if (!isValid(credential)) {
            record("BIND", id, actor, "DENIED", "Inactive credential");
            throw SecurityException("Credential is inactive or expired");
        }

        if (
            credential.scope == CredentialScope::System &&
            !allowSystem
        ) {
            record("BIND", id, actor, "DENIED", "System scope restriction");
            throw SecurityException("System credential access denied");
        }

        if (credential.type != requiredType) {
            throw SecurityException("Credential type mismatch");
        }

        if (pipeline.empty() || actor.empty()) {
            throw ValidationException("Pipeline and actor are required");
        }

        record("BIND", id, actor, "SUCCESS", pipeline);

        return secretVault.at(id);
    }

    void rotate(
        const string& id,
        SecretMaterial replacement,
        const string& actor
    ) {
        auto iterator = metadata.find(id);

        if (iterator == metadata.end()) {
            throw NotFoundException("Credential not found");
        }

        Credential& credential = iterator->second;

        if (credential.status == CredentialStatus::Revoked) {
            throw SecurityException("Revoked credential cannot be rotated");
        }

        if (replacement.value.empty()) {
            throw ValidationException("Replacement secret cannot be empty");
        }

        if (
            credential.type == CredentialType::UsernamePassword &&
            (!replacement.usesUsername || replacement.username.empty())
        ) {
            throw ValidationException("Username is required");
        }

        secretVault.at(id) = replacement;
        credential.version++;
        credential.status = CredentialStatus::Active;
        credential.hasExpiration = false;

        record(
            "ROTATE",
            id,
            actor,
            "SUCCESS",
            "Version " + to_string(credential.version)
        );
    }

    void revoke(const string& id, const string& actor) {
        auto iterator = metadata.find(id);

        if (iterator == metadata.end()) {
            throw NotFoundException("Credential not found");
        }

        iterator->second.status = CredentialStatus::Revoked;
        secretVault.erase(id);

        record("REVOKE", id, actor, "SUCCESS");
    }

    vector<Credential> list() const {
        vector<Credential> result;

        for (const auto& entry : metadata) {
            result.push_back(entry.second);
        }

        return result;
    }

    const vector<AuditEvent>& auditLog() const {
        return audit;
    }
};

class PipelineConfiguration {
private:
    string name;
    vector<string> credentialIds;

public:
    PipelineConfiguration(
        string pipelineName,
        vector<string> ids
    ) : name(move(pipelineName)), credentialIds(move(ids)) {}

    bool validate(const CredentialStore& store) const {
        if (name.empty()) {
            throw ValidationException("Pipeline name is required");
        }

        set<string> uniqueIds;

        for (const string& id : credentialIds) {
            if (!uniqueIds.insert(id).second) {
                throw ValidationException("Duplicate credential binding");
            }

            const Credential& credential = store.getMetadata(id);

            if (credential.status != CredentialStatus::Active) {
                throw SecurityException("Inactive credential: " + id);
            }

            if (credential.scope == CredentialScope::System) {
                throw SecurityException("System credential not allowed");
            }
        }

        return true;
    }
};

class JenkinsfileScanner {
public:
    static vector<string> scan(const string& content) {
        vector<pair<string, regex>> rules = {
            {
                "Possible hardcoded password or token",
                regex(
                    R"((password|secret|token|api_key)\s*=\s*['"][^'"]+)",
                    regex::icase
                )
            },
            {
                "Private key material",
                regex(R"(-----BEGIN [A-Z ]*PRIVATE KEY-----)")
            },
            {
                "Bearer token",
                regex(
                    R"(authorization\s*:\s*bearer\s+\S+)",
                    regex::icase
                )
            }
        };

        vector<string> findings;

        for (const auto& rule : rules) {
            if (regex_search(content, rule.second)) {
                findings.push_back(rule.first);
            }
        }

        return findings;
    }
};

int main() {
    try {
        cout << "JENKINS CREDENTIALS MANAGEMENT\n";
        cout << string(55, '=') << "\n\n";

        CredentialStore store;

        store.add(
            "github-deploy-token",
            "GitHub deployment token",
            "devops-team",
            CredentialType::SecretText,
            CredentialScope::Global,
            {"", "SIMULATED_GITHUB_TOKEN", false}
        );

        store.add(
            "docker-registry",
            "Docker registry authentication",
            "platform-team",
            CredentialType::UsernamePassword,
            CredentialScope::Global,
            {
                "build-user",
                "SIMULATED_REGISTRY_PASSWORD",
                true
            }
        );

        store.add(
            "production-ssh",
            "Production SSH private key",
            "infrastructure-team",
            CredentialType::SSHPrivateKey,
            CredentialScope::System,
            {"", "SIMULATED_PRIVATE_KEY", false}
        );

        cout << "1. Credential inventory\n";

        for (const Credential& credential : store.list()) {
            cout
                << credential.id << " | "
                << toString(credential.type) << " | "
                << toString(credential.scope) << " | "
                << toString(credential.status) << " | "
                << "Version " << credential.version << "\n";
        }

        cout << "\n2. Pipeline configuration validation\n";

        PipelineConfiguration pipeline(
            "release-pipeline",
            {
                "github-deploy-token",
                "docker-registry"
            }
        );

        cout << "Valid: " << boolalpha << pipeline.validate(store) << "\n";

        cout << "\n3. Credential binding\n";

        const SecretMaterial& registry = store.resolve(
            "docker-registry",
            "release-pipeline",
            "build-agent",
            CredentialType::UsernamePassword
        );

        cout << "Authenticated as: " << registry.username << "\n";

        cout << "\n4. Credential rotation\n";

        store.rotate(
            "github-deploy-token",
            {"", "SIMULATED_ROTATED_TOKEN", false},
            "security-admin"
        );

        cout
            << "New version: "
            << store.getMetadata("github-deploy-token").version
            << "\n";

        cout << "\n5. Restricted system credential\n";

        try {
            store.resolve(
                "production-ssh",
                "release-pipeline",
                "build-agent",
                CredentialType::SSHPrivateKey
            );
        } catch (const SecurityException& error) {
            cout << "Access denied: " << error.what() << "\n";
        }

        cout << "\n6. Jenkinsfile security inspection\n";

        const string jenkinsfile = R"(
            pipeline {
                stages {
                    stage('Build') {
                        steps {
                            echo 'Build application'
                        }
                    }
                }
            }
        )";

        auto findings = JenkinsfileScanner::scan(jenkinsfile);

        if (findings.empty()) {
            cout << "No obvious hardcoded secrets detected\n";
        } else {
            for (const string& finding : findings) {
                cout << finding << "\n";
            }
        }

        cout << "\n7. Credential revocation\n";

        store.revoke(
            "github-deploy-token",
            "security-admin"
        );

        try {
            store.resolve(
                "github-deploy-token",
                "release-pipeline",
                "build-agent",
                CredentialType::SecretText
            );
        } catch (const SecurityException& error) {
            cout << "Access denied: " << error.what() << "\n";
        }

        cout << "\n8. Audit log\n";

        for (const AuditEvent& event : store.auditLog()) {
            cout
                << event.action << " | "
                << event.credentialId << " | "
                << event.actor << " | "
                << event.outcome << " | "
                << event.details << "\n";
        }

        cout << "\n9. Automated checks\n";

        if (store.getMetadata("github-deploy-token").version != 2) {
            throw runtime_error("Rotation validation failed");
        }

        if (
            store.getMetadata("github-deploy-token").status
            != CredentialStatus::Revoked
        ) {
            throw runtime_error("Revocation validation failed");
        }

        try {
            store.add(
                "bad id",
                "Invalid credential",
                "admin",
                CredentialType::SecretText,
                CredentialScope::Global,
                {"", "secret", false}
            );

            throw runtime_error("Invalid credential ID accepted");
        } catch (const ValidationException&) {
            cout << "Invalid ID correctly rejected\n";
        }

        cout << "All checks passed.\n";

    } catch (const exception& error) {
        cerr << "ERROR: " << error.what() << "\n";
        return 1;
    }

    return 0;
}

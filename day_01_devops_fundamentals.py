# ============================================================
# DAY 01: DEVOPS FUNDAMENTALS
# ============================================================

print("DAY 01 - DEVOPS FUNDAMENTALS")


# ============================================================
# 1. WHAT IS DEVOPS?
# ============================================================

print("\n1. WHAT IS DEVOPS?")

print("DevOps is a set of practices that brings")
print("software development and IT operations closer together.")
print("Its goal is to improve the speed, reliability,")
print("automation, and continuous delivery of software.")


# ============================================================
# 2. DEVELOPMENT AND OPERATIONS
# ============================================================

print("\n2. DEVELOPMENT AND OPERATIONS")

development = [
    "Write Code",
    "Build Features",
    "Fix Bugs",
    "Test Software"
]

operations = [
    "Deploy Applications",
    "Manage Infrastructure",
    "Monitor Systems",
    "Maintain Reliability"
]

print("Development:")

for activity in development:
    print("-", activity)

print("\nOperations:")

for activity in operations:
    print("-", activity)


# ============================================================
# 3. DEVOPS LIFECYCLE
# ============================================================

print("\n3. DEVOPS LIFECYCLE")

devops_lifecycle = [
    "Plan",
    "Code",
    "Build",
    "Test",
    "Release",
    "Deploy",
    "Operate",
    "Monitor"
]

for stage in devops_lifecycle:
    print("-", stage)


# ============================================================
# 4. VERSION CONTROL
# ============================================================

print("\n4. VERSION CONTROL")

print("Version control tracks changes made to source code.")

repository = {
    "name": "my-application",
    "branch": "main",
    "version": "1.0"
}

print("Repository:", repository["name"])
print("Branch:", repository["branch"])
print("Version:", repository["version"])


# ============================================================
# 5. AUTOMATION
# ============================================================

print("\n5. AUTOMATION")

manual_tasks = [
    "Build application",
    "Run tests",
    "Deploy application"
]

print("Tasks that can be automated:")

for task in manual_tasks:
    print("-", task)

print("\nAutomation reduces repetitive manual work")
print("and helps improve consistency.")


# ============================================================
# 6. CONTINUOUS INTEGRATION
# ============================================================

print("\n6. CONTINUOUS INTEGRATION")

print("Continuous Integration (CI) involves frequently")
print("integrating code changes and automatically")
print("building and testing the application.")


# ============================================================
# 7. CONTINUOUS DELIVERY
# ============================================================

print("\n7. CONTINUOUS DELIVERY")

print("Continuous Delivery keeps software in a")
print("deployable state so that changes can be released")
print("reliably when required.")


# ============================================================
# 8. CI/CD PIPELINE
# ============================================================

print("\n8. BASIC CI/CD PIPELINE")

pipeline = [
    "Developer commits code",
    "Code is built",
    "Automated tests run",
    "Application is packaged",
    "Application is deployed"
]

for step_number, step in enumerate(pipeline, start=1):
    print(step_number, "->", step)


# ============================================================
# 9. INFRASTRUCTURE
# ============================================================

print("\n9. INFRASTRUCTURE")

infrastructure = [
    "Servers",
    "Networks",
    "Storage",
    "Databases",
    "Containers"
]

for component in infrastructure:
    print("-", component)


# ============================================================
# 10. MONITORING
# ============================================================

print("\n10. MONITORING")

system_metrics = {
    "CPU Usage": 65,
    "Memory Usage": 72,
    "Application Status": "Running"
}

for metric, value in system_metrics.items():
    print(metric + ":", value)


# ============================================================
# 11. DEVOPS CULTURE
# ============================================================

print("\n11. DEVOPS CULTURE")

principles = [
    "Collaboration",
    "Automation",
    "Continuous Improvement",
    "Fast Feedback",
    "Shared Responsibility"
]

for principle in principles:
    print("-", principle)


# ============================================================
# 12. BASIC DEVOPS FLOW
# ============================================================

print("\n12. BASIC DEVOPS FLOW")

print("""
Plan
  ↓
Code
  ↓
Build
  ↓
Test
  ↓
Release
  ↓
Deploy
  ↓
Operate
  ↓
Monitor
  ↓
Feedback
  ↓
Improve
""")


# ============================================================
# SUMMARY
# ============================================================

print("=" * 60)
print("DAY 01 COMPLETED")
print("=" * 60)

print("""
Today you learned:

1. What DevOps is
2. Development and Operations
3. DevOps lifecycle
4. Version control
5. Automation
6. Continuous Integration
7. Continuous Delivery
8. CI/CD pipeline
9. Infrastructure
10. Monitoring
11. DevOps culture
12. Basic DevOps workflow
""")

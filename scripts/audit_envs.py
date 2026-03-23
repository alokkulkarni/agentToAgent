#!/usr/bin/env python3
"""Audit: cross-reference every os.getenv() key in each service against its .env file."""
import os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVICES = {
    "registry":       ("services/registry/.env",               ["services/registry/app.py"]),
    "mcp_registry":   ("services/mcp_registry/.env",           ["services/mcp_registry/app.py"]),
    "mcp_gateway":    ("services/mcp_gateway/.env",            ["services/mcp_gateway/app.py"]),
    "orchestrator":   ("services/orchestrator/.env",           ["services/orchestrator/app.py",
                                                                "services/orchestrator/ha_database.py",
                                                                "shared/distributed_state.py"]),
    "research_agent": ("services/agents/research_agent/.env",  ["services/agents/research_agent/app.py"]),
    "code_analyzer":  ("services/agents/code_analyzer/.env",   ["services/agents/code_analyzer/app.py"]),
    "data_processor": ("services/agents/data_processor/.env",  ["services/agents/data_processor/app.py"]),
    "task_executor":  ("services/agents/task_executor/.env",   ["services/agents/task_executor/app.py"]),
    "observer":       ("services/agents/observer/.env",        ["services/agents/observer/app.py"]),
    "math_agent":     ("services/agents/math_agent/.env",      ["services/agents/math_agent/app.py"]),
    "calculator":     ("services/mcp_servers/calculator/.env", ["services/mcp_servers/calculator/app.py"]),
    "file_ops":       ("services/mcp_servers/file_ops/.env",   ["services/mcp_servers/file_ops/app.py"]),
    "database":       ("services/mcp_servers/database/.env",   ["services/mcp_servers/database/app.py"]),
    "web_search":     ("services/mcp_servers/web_search/.env", ["services/mcp_servers/web_search/app.py"]),
}

# These are optional — apps fall back to ~/.aws credential chain when missing
AWS_OPTIONAL = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"}

def env_keys(path):
    keys = set()
    full = os.path.join(BASE, path)
    if not os.path.exists(full):
        return keys
    for line in open(full):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=")[0].strip())
    return keys

def code_keys(paths):
    keys = set()
    pat = re.compile(r'os\.(?:getenv|environ\.get)\(\s*["\']([A-Z_][A-Z0-9_]*)["\']')
    for path in paths:
        full = os.path.join(BASE, path)
        if not os.path.exists(full):
            continue
        for m in pat.finditer(open(full).read()):
            keys.add(m.group(1))
    return keys

print(f"\n{'SERVICE':<22} STATUS    GAPS (vars in code but not in .env)")
print("-" * 90)

all_ok = True
for svc, (env_file, py_files) in SERVICES.items():
    in_env  = env_keys(env_file)
    in_code = code_keys(py_files)
    gaps = in_code - in_env - AWS_OPTIONAL
    if gaps:
        all_ok = False
        print(f"  {svc:<22} GAP    {sorted(gaps)}")
    else:
        print(f"  {svc:<22} OK")

print()
if all_ok:
    print("PASS: every os.getenv() key is present in the service .env")
else:
    print("FAIL: gaps found — need to add missing keys to the respective .env files")
print()

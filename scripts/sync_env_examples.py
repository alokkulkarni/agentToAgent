#!/usr/bin/env python3
"""Sync .env.example files from .env files (strip real secrets, keep structure)."""
import os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVICE_ENVS = [
    "services/registry/.env",
    "services/mcp_registry/.env",
    "services/mcp_gateway/.env",
    "services/orchestrator/.env",
    "services/agents/research_agent/.env",
    "services/agents/code_analyzer/.env",
    "services/agents/data_processor/.env",
    "services/agents/task_executor/.env",
    "services/agents/observer/.env",
    "services/agents/math_agent/.env",
    "services/mcp_servers/calculator/.env",
    "services/mcp_servers/file_ops/.env",
    "services/mcp_servers/database/.env",
    "services/mcp_servers/web_search/.env",
]

# Values that should appear as placeholders in .env.example
PLACEHOLDER_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
}

for rel in SERVICE_ENVS:
    src = os.path.join(BASE, rel)
    dst = src + ".example"
    if not os.path.exists(src):
        print(f"  SKIP (missing): {rel}")
        continue
    lines = open(src).readlines()
    out = []
    for line in lines:
        stripped = line.rstrip("\n")
        if "=" in stripped and not stripped.startswith("#"):
            key, _, val = stripped.partition("=")
            key = key.strip()
            if key in PLACEHOLDER_KEYS and val and val not in ("", "your_access_key_here", "your_secret_key_here"):
                out.append(f"{key}=your_{key.lower()}_here\n")
                continue
        out.append(line)
    with open(dst, "w") as f:
        f.writelines(out)
    print(f"  synced: {rel}.example")

print("\nAll .env.example files synced.")

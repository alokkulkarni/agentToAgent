#!/usr/bin/env python3
"""
Code Analyzer Interactive Workflow Example
==========================================

This example demonstrates an interactive code analysis workflow where:
1. We submit some "buggy" code to the CodeAnalyzer agent
2. The agent detects multiple issues (>5) and asks for guidance
3. We respond via WebSocket to tell it which issues to fix
4. The agent applies the fixes based on our choice

Usage:
    python3 examples/code_analyzer_interactive.py
"""

import asyncio
import websockets
import json
import sys
import requests
from datetime import datetime

# The buggy code to analyze
BUGGY_CODE = """
import os
import sqlite3
from flask import Flask, request

app = Flask(__name__)

# Issue 1: Hardcoded secret (Critical)
SECRET_KEY = "my_super_secret_password_123"

# Issue 2: Global variable for connection (High)
conn = sqlite3.connect('users.db')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    # Issue 3: SQL Injection (Critical)
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    
    # Issue 4: Using global connection (High)
    cursor = conn.cursor()
    cursor.execute(query)
    user = cursor.fetchone()
    
    if user:
        # Issue 5: Plain text logging of sensitive info (Medium)
        print(f"User logged in: {username} with password {password}")
        return "Welcome!"
    else:
        return "Login failed"

@app.route('/get_file')
def get_file():
    filename = request.args.get('file')
    # Issue 6: Path Traversal (Critical)
    # Issue 7: No error handling (Medium)
    with open(filename, 'r') as f:
        return f.read()

if __name__ == '__main__':
    # Issue 8: Debug mode in production (High)
    app.run(debug=True, host='0.0.0.0')
"""

class CodeAnalysisClient:
    """Interactive client for Code Analysis"""
    
    def __init__(self, orchestrator_url: str = "ws://localhost:8100"):
        self.orchestrator_url = orchestrator_url
        self.rest_url = "http://localhost:8100"
        self.websocket = None
        self.workflow_id = None
        
    async def connect(self, workflow_id: str):
        """Connect to workflow WebSocket with retry"""
        self.workflow_id = workflow_id
        uri = f"{self.orchestrator_url}/ws/workflow/{workflow_id}"
        
        print(f"\n🔌 Connecting to WebSocket: {uri}")
        
        max_retries = 5
        for i in range(max_retries):
            try:
                self.websocket = await websockets.connect(uri, open_timeout=20)
                print(f"✅ Connected to workflow: {workflow_id}\n")
                return
            except Exception as e:
                print(f"   ⚠️ Connection attempt {i+1}/{max_retries} failed: {e}")
                if i < max_retries - 1:
                    await asyncio.sleep(2)
        
        raise Exception("Failed to connect to WebSocket")
        
    async def run(self):
        """Run the full workflow"""
        # 1. Submit Workflow
        print(f"📝 Submitting buggy code for analysis...")
        print(f"   (Code has SQL injection, secrets, path traversal, etc.)")
        
        task = f"Analyze and improve this Python code:\n\n{BUGGY_CODE}"
        workflow_id = f"code_fix_{int(datetime.now().timestamp())}"
        
        try:
            resp = requests.post(
                f"{self.rest_url}/api/workflow/execute",
                json={
                    "workflow_id": workflow_id,
                    "task_description": task,
                    "async": True
                },
                timeout=30
            )
            resp.raise_for_status()
            print(f"✅ Workflow started: {workflow_id}")
        except Exception as e:
            print(f"❌ Failed to start workflow: {e}")
            return

        # 2. Monitor via WebSocket
        await self.connect(workflow_id)
        
        try:
            async for message in self.websocket:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "step_started":
                    step = data.get("step", {})
                    print(f"   🔄 Step {step.get('step_number')}: {step.get('description')}")
                    print(f"      (Agent: {step.get('agent')})")
                    
                elif msg_type == "step_completed":
                    print(f"   ✅ Step completed")
                    
                elif msg_type == "user_input_required":
                    # This is the interactive part!
                    interaction = data.get("interaction", {})
                    req_id = interaction.get("request_id")
                    question = interaction.get("question")
                    options = interaction.get("options", [])
                    
                    print(f"\n{'='*80}")
                    print(f"🛑 INTERVENTION REQUIRED")
                    print(f"{'='*80}")
                    print(f"🤖 Agent asks: {question}")
                    print(f"\nOptions:")
                    for i, opt in enumerate(options, 1):
                        print(f"  {i}. {opt}")
                    
                    # Automatically select "Fix only critical and high priority issues"
                    # In a real app, you would prompt input() here
                    my_choice = "Fix only critical and high priority issues"
                    
                    print(f"\n💡 Auto-selecting: '{my_choice}'")
                    
                    await self.websocket.send(json.dumps({
                        "type": "user_response",
                        "request_id": req_id,
                        "response": my_choice
                    }))
                    print(f"📤 Response sent!")
                    
                elif msg_type == "workflow_completed":
                    print(f"\n🎉 Workflow Finished!")
                    result = data.get("result", {})
                    
                    # Print the final result (the fixed code)
                    results_list = result.get("results", [])
                    for res in results_list:
                        if res.get("capability") == "suggest_improvements":
                            final_output = res.get("result", {})
                            print(f"\n{'='*80}")
                            print(f"📊 Analysis Summary:")
                            print(f"{'='*80}")
                            summary = final_output.get("issue_summary", {})
                            print(f"Found {summary.get('total')} issues:")
                            print(f"  - Critical: {summary.get('critical')}")
                            print(f"  - High:     {summary.get('high')}")
                            print(f"  - Medium:   {summary.get('medium')}")
                            
                            print(f"\n{'='*80}")
                            print(f"🛠️  Improved Code (Critical & High fixes only):")
                            print(f"{'='*80}")
                            print(final_output.get("suggestions", "No code returned"))
                    break
                    
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        finally:
            await self.websocket.close()

if __name__ == "__main__":
    client = CodeAnalysisClient()
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")

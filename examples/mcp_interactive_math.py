#!/usr/bin/env python3
"""
MCP Interactive Math Workflow Example
=====================================

This example demonstrates an interactive workflow where:
1. We submit an incomplete math task to the MathAgent
2. The agent detects missing parameters (e.g., the second number)
3. The agent asks for the missing input via WebSocket
4. We provide the missing number
5. The agent calls the MCP Calculator Tool to perform the calculation

Usage:
    python3 examples/mcp_interactive_math.py
"""

import asyncio
import websockets
import json
import requests
from datetime import datetime

# The incomplete task
# Note: We are deliberately being vague so the orchestrator maps it to 'calculate' 
# but passes incomplete parameters, or we force the parameters to be incomplete.
# Since we can't easily force partial parameters via natural language planning without 
# risk of it just failing, we will cheat slightly and inject a task directly to the agent 
# or rely on the orchestrator passing partial params if we phrase it right.
# Better yet, we can't easily inject partial params via natural language. 
# So we will define a workflow that has a specific plan.

# ACTUALLY: The easiest way to demo this is to submit a task description that implies 
# missing info, like "Calculate the sum of 50 and [ask user]" - but the LLM planner 
# might just hallucinate.
# Instead, we will manually trigger the agent via the orchestrator using a pre-defined plan
# OR we rely on the MathAgent's new interactive logic.

# Let's try natural language: "Calculate the sum of 100 and a number I will provide later"
# The planner might try to put a placeholder.
# If the planner puts "0" or guesses, we fail.
# If the planner fails to extract 'b', it might send null.
# Let's see.

TASK_DESCRIPTION = "Add 100 to a number that I will provide"

class MCPInteractiveClient:
    """Interactive client for MCP Math"""
    
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
        print(f"📝 Submitting incomplete math task...")
        print(f"   Task: '{TASK_DESCRIPTION}'")
        
        workflow_id = f"mcp_math_{int(datetime.now().timestamp())}"
        
        try:
            resp = requests.post(
                f"{self.rest_url}/api/workflow/execute",
                json={
                    "workflow_id": workflow_id,
                    "task_description": TASK_DESCRIPTION,
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
                    
                elif msg_type == "user_input_required":
                    # This is the interactive part!
                    interaction = data.get("interaction", {})
                    req_id = interaction.get("request_id")
                    question = interaction.get("question")
                    
                    print(f"\n{'='*80}")
                    print(f"🛑 INTERVENTION REQUIRED")
                    print(f"{'='*80}")
                    print(f"🤖 Agent asks: {question}")
                    
                    # We provide the missing number
                    my_response = "42"
                    print(f"\n💡 Providing missing number: '{my_response}'")
                    
                    await self.websocket.send(json.dumps({
                        "type": "user_response",
                        "request_id": req_id,
                        "response": my_response
                    }))
                    print(f"📤 Response sent!")
                    
                elif msg_type == "workflow_completed":
                    print(f"\n🎉 Workflow Finished!")
                    result = data.get("result", {})
                    
                    # Print the final result
                    results_list = result.get("results", [])
                    for res in results_list:
                        if res.get("capability") == "calculate":
                            final_output = res.get("result", {})
                            print(f"\n{'='*80}")
                            print(f"📊 Calculation Result:")
                            print(f"{'='*80}")
                            print(f"Operation: {final_output.get('operation')}")
                            print(f"Input A:   {final_output.get('a')}")
                            print(f"Input B:   {final_output.get('b')}")
                            print(f"Result:    {final_output.get('result')}")
                            
                            # Verify it called MCP
                            mcp_resp = final_output.get("mcp_response", {})
                            if mcp_resp:
                                print(f"\n(✅ Verified: Executed via MCP Calculator Tool)")
                    break
                    
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
        finally:
            await self.websocket.close()

if __name__ == "__main__":
    client = MCPInteractiveClient()
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")

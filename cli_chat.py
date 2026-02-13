#!/usr/bin/env python3
"""
AgentToAgent CLI Chat Application
=================================

A terminal-based chat interface for interacting with the AgentToAgent Orchestrator.
Mimics the experience of using an AI assistant like GitHub Copilot CLI.

Features:
- Submit tasks using natural language
- Real-time streaming of agent thoughts and execution steps
- Interactive prompts when agents need clarification or decisions
- Rich formatting of outputs

Usage:
    python3 cli_chat.py
"""

import asyncio
import sys
import json
import uuid
import datetime
import argparse
from typing import Optional, Dict, Any

# Third-party imports (standard in the project venv)
try:
    import aiohttp
    import websockets
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.status import Status
    from rich.live import Live
    from rich.table import Table
    from rich import box
except ImportError:
    print("Missing dependencies. Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "aiohttp", "websockets"])
    import aiohttp
    import websockets
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.status import Status
    from rich.live import Live
    from rich.table import Table
    from rich import box

# Configuration
ORCHESTRATOR_URL = "http://127.0.0.1:8100"
WS_URL = "ws://127.0.0.1:8100"

console = Console()

class OrchestratorClient:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_workflow_id: Optional[str] = None
        self.websocket = None
        
        # Load or create persistent session ID
        self.session_file = ".agent_session"
        try:
            with open(self.session_file, "r") as f:
                self.session_id = f.read().strip()
                if not self.session_id: raise ValueError("Empty session file")
        except:
            self.session_id = f"sess_{uuid.uuid4().hex[:8]}"
            with open(self.session_file, "w") as f:
                f.write(self.session_id)
        
        console.print(f"[dim]Session ID: {self.session_id}[/dim]")
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def check_health(self) -> bool:
        try:
            async with self.session.get(f"{ORCHESTRATOR_URL}/health") as response:
                return response.status == 200
        except:
            return False

    async def start_workflow(self, task: str) -> Dict[str, Any]:
        """Start a new workflow via REST"""
        workflow_id = f"cli_{uuid.uuid4().hex[:8]}"
        payload = {
            "workflow_id": workflow_id,
            "session_id": self.session_id,
            "task_description": task,
            "async": True
        }
        
        try:
            # Force a new session for the POST request to avoid connection reuse issues
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{ORCHESTRATOR_URL}/api/workflow/execute", json=payload) as response:
                    if response.status not in [200, 202]:
                        text = await response.text()
                        raise Exception(f"Failed to start workflow: {text}")
                    return await response.json()
        except Exception as e:
            # Check if self.session needs reset
            if self.session and self.session.closed:
                 self.session = aiohttp.ClientSession()
            raise Exception(f"Connection error: {str(e)}")

    async def connect_websocket(self, workflow_id: str):
        """Connect to workflow status stream"""
        uri = f"{WS_URL}/ws/workflow/{workflow_id}"
        self.websocket = await websockets.connect(uri)
        return self.websocket

    async def send_response(self, request_id: str, response: str):
        """Send user response to an interaction request"""
        if self.websocket:
            await self.websocket.send(json.dumps({
                "type": "user_response",
                "request_id": request_id,
                "response": response
            }))

async def handle_workflow(client: OrchestratorClient, task_description: str, resume_context: Optional[dict] = None) -> Optional[dict]:
    """
    Handle the lifecycle of a single workflow execution.
    Returns a 'pause context' if the workflow was interrupted, or None if completed/failed.
    """
    
    workflow_id = None
    
    # 1. Start or Resume workflow
    if resume_context:
        workflow_id = resume_context["workflow_id"]
        console.print(f"[dim]Resuming workflow ID: {workflow_id}[/dim]")
    else:
        # Start new
        try:
            start_result = await client.start_workflow(task_description)
            workflow_id = start_result.get("workflow_id")
            console.print(f"[dim]Started workflow ID: {workflow_id}[/dim]")
        except Exception as e:
            console.print(f"[bold red]Error starting workflow:[/bold red] {e}")
            return None

    # 2. Connect to WebSocket
    try:
        websocket = await client.connect_websocket(workflow_id)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to event stream:[/bold red] {e}")
        return None

    # 3. Listen for events
    step_status = None
    current_step_desc = "Initializing..."
    
    # Timeout configuration (10 seconds interval check for responsiveness)
    TIMEOUT_SECONDS = 10.0 
    
    try:
        while True:
            try:
                # Wait for next message with timeout
                message = await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT_SECONDS)
                
                data = json.loads(message)
                msg_type = data.get("type")
                
                # --- Event Handling ---
                
                if msg_type == "connection_established":
                    pass 
                    
                elif msg_type == "workflow_started":
                    if not resume_context:
                        console.print(Panel(f"[bold]Task:[/bold] {task_description}", title="Workflow Started", border_style="blue"))
                    
                elif msg_type == "step_started":
                    step = data.get("step", {})
                    step_num = step.get("step_number")
                    capability = step.get("capability")
                    agent = step.get("agent")
                    desc = step.get("description")
                    
                    console.print(f"\n[bold blue]Step {step_num}:[/bold blue] {desc}")
                    console.print(f"   [dim]Using agent [cyan]{agent}[/cyan] for [cyan]{capability}[/cyan][/dim]")
                    
                elif msg_type == "step_completed":
                    step = data.get("step", {})
                    result = data.get("result", {})
                    
                    # Try to format the result nicely
                    content = None
                    
                    # Helper to extract scalar for display
                    def extract_display_value(d):
                        if not isinstance(d, dict): return d
                        for k in ["result", "answer", "output", "value"]:
                            if k in d:
                                val = d[k]
                                if isinstance(val, dict): return extract_display_value(val)
                                return val
                        return d

                    if isinstance(result, dict):
                        # Use the same extraction logic for display
                        extracted = extract_display_value(result)
                        if extracted != result:
                            content = extracted
                        elif "answer" in result: content = result["answer"]
                        elif "analysis" in result: content = result["analysis"]
                        elif "report" in result: content = result["report"]
                        elif "explanation" in result: content = result["explanation"]
                        elif "suggestions" in result: content = result["suggestions"]
                        elif "comparison" in result: content = result["comparison"]
                        elif "summary" in result: content = result["summary"]
                        elif "result" in result: content = result["result"] 
                        elif "output" in result: content = result["output"]
                        else: content = result # Fallback to showing full dict if no scalar found
                    elif result is not None:
                        content = result # Direct value result
                    
                    if content is not None:
                        # If content is simple (number/short string), print inline
                        if isinstance(content, (int, float)) or (isinstance(content, str) and len(str(content)) < 100):
                             console.print(Panel(f"[bold green]{content}[/bold green]", title=f"Result (Step {step.get('step_number')})", border_style="green"))
                        else:
                             console.print(Panel(Markdown(str(content)), title=f"Result (Step {step.get('step_number')})", border_style="green"))
                    else:
                        console.print(f"   [green]✓ Step completed[/green]")

                elif msg_type == "user_input_required":
                    # Handle Interaction
                    interaction = data.get("interaction", {})
                    request_id = interaction.get("request_id")
                    question = interaction.get("question")
                    input_type = interaction.get("input_type", "text")
                    options = interaction.get("options", [])
                    agent_name = interaction.get("agent", "Agent")
                    
                    console.print("\n")
                    console.rule(f"[yellow]Input Required ({agent_name})[/yellow]")
                    console.print(f"[bold]{question}[/bold]")
                    
                    response = None
                    
                    if options and len(options) > 0:
                        # Choice input
                        for i, opt in enumerate(options, 1):
                            console.print(f"  [cyan]{i}.[/cyan] {opt}")
                        
                        console.print(f"  [cyan]0.[/cyan] [italic]Pause and start new task...[/italic]")
                        
                        while True:
                            selection = Prompt.ask("Select an option", default="1")
                            
                            # Check for new task interruption
                            if selection == "0":
                                console.print("[yellow]Pausing current workflow to switch context...[/yellow]")
                                return {
                                    "workflow_id": workflow_id,
                                    "task": task_description,
                                    "paused_at": datetime.datetime.now().isoformat()
                                }
                                
                            try:
                                idx = int(selection) - 1
                                if 0 <= idx < len(options):
                                    response = options[idx]
                                    break
                                else:
                                    console.print("[red]Invalid selection[/red]")
                            except:
                                if selection in options:
                                    response = selection
                                    break
                                console.print("[red]Please enter a valid number or '0' to switch tasks[/red]")
                    else:
                        # Text input
                        console.print("[dim](Type '::new' to pause and start a new task)[/dim]")
                        response = Prompt.ask("Answer")
                        if response.strip() == "::new":
                            console.print("[yellow]Pausing current workflow to switch context...[/yellow]")
                            return {
                                "workflow_id": workflow_id,
                                "task": task_description,
                                "paused_at": datetime.datetime.now().isoformat()
                            }
                    
                    # Send response
                    await client.send_response(request_id, response)
                    console.print("[dim]Response sent, resuming workflow...[/dim]")
                    
                elif msg_type == "workflow_completed":
                    console.print("\n")
                    console.rule("[bold green]Workflow Completed[/bold green]")
                    result = data.get("result", {})
                    
                    if "reflection" in result:
                        reflection = result["reflection"]
                        if isinstance(reflection, dict) and "summary" in reflection:
                            console.print(Panel(reflection["summary"], title="Orchestrator Reflection"))
                    
                    return None # Completed
                    
                elif msg_type == "error" or msg_type == "step_error":
                    error_msg = data.get("error") or data.get("message")
                    console.print(f"[bold red]Error:[/bold red] {error_msg}")
                    return None

            except asyncio.TimeoutError:
                # Timeout occurred - ask user what to do
                console.print(f"\n[yellow]⚠️  No response from agent for {TIMEOUT_SECONDS}s[/yellow]")
                action = Prompt.ask(
                    "What would you like to do?",
                    choices=["wait", "quit", "new"],
                    default="wait",
                    show_choices=True
                )
                
                if action == "wait":
                    console.print("[dim]Continuing to wait...[/dim]")
                    continue 
                elif action == "new":
                    console.print("[yellow]Pausing current workflow to switch context...[/yellow]")
                    return {
                        "workflow_id": workflow_id,
                        "task": task_description,
                        "paused_at": datetime.datetime.now().isoformat()
                    }
                elif action == "quit":
                    return None 

    except websockets.exceptions.ConnectionClosed:
        console.print("[red]Connection lost to orchestrator[/red]")
        return None
    
    return None

async def main():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]AgentToAgent CLI[/bold cyan]\n"
        "Interactive Multi-Agent Orchestrator Client\n"
        "[dim]v1.1.0 (Multi-Task Support)[/dim]",
        box=box.ROUNDED
    ))

    async with OrchestratorClient() as client:
        # Check connection
        if not await client.check_health():
            console.print(f"[bold red]Could not connect to Orchestrator at {ORCHESTRATOR_URL}[/bold red]")
            console.print("Please ensure services are running: [bold]./start_services.sh[/bold]")
            return

        console.print("[green]●[/green] Connected to Orchestrator")
        console.print("Type [bold red]exit[/bold red] or [bold red]quit[/bold red] to close.\n")

        # Stack to hold paused workflows
        paused_workflows = []

        while True:
            try:
                # Show pending workflows if any
                if paused_workflows:
                    console.print(f"\n[dim]Paused workflows: {len(paused_workflows)}[/dim]")
                
                task = Prompt.ask("\n[bold green]What would you like to do?[/bold green]")
                
                if task.lower() in ['exit', 'quit', 'q']:
                    break
                
                if not task.strip():
                    continue
                
                # Execute workflow
                result_context = await handle_workflow(client, task)
                
                # If we got a context back, it means we paused
                if result_context and isinstance(result_context, dict):
                    paused_workflows.append(result_context)
                    
                    # Ask for the new task immediately
                    new_task = Prompt.ask("\n[bold magenta]Enter your new request[/bold magenta]")
                    if new_task.lower() in ['exit', 'quit']:
                        break
                        
                    # Run the new task
                    await handle_workflow(client, new_task)
                    
                    # After new task is done, check paused stack
                    if paused_workflows:
                        last_paused = paused_workflows[-1]
                        resume = Confirm.ask(f"\nDo you want to resume the paused task: [bold]'{last_paused['task']}'[/bold]?", default=True)
                        if resume:
                            paused_workflows.pop()
                            await handle_workflow(client, last_paused['task'], resume_context=last_paused)
                        else:
                            console.print("[dim]Task remains paused in background[/dim]")

            except KeyboardInterrupt:
                console.print("\n[dim]Operation cancelled[/dim]")
                continue
            except Exception as e:
                console.print(f"[bold red]Unexpected error:[/bold red] {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")

# A2A Multi-Agent System - Testing Guide

## What Has Been Fixed

### 1. **Detailed Workflow Execution Logging**
   - Enhanced orchestrator to show step-by-step execution details
   - Added execution log with discovery, planning, and execution phases
   - Each step now shows:
     - Agent selection
     - Parameters sent
     - Results received
     - Success/failure status

### 2. **Improved LLM Planning**
   - Better prompt engineering for execution plan generation
   - Explicit capability name matching
   - JSON response validation and cleanup
   - Fallback to default plan if LLM fails
   - Handles markdown code blocks in LLM responses

### 3. **Enhanced Test Output**
   - Test 5 now shows complete workflow details:
     - Execution plan with reasoning
     - Each step's capability and agent
     - Results from each step
     - Execution log with status for each phase

### 4. **Better Error Handling**
   - AWS credential validation
   - Bedrock API error handling with fallback
   - JSON parsing with cleanup
   - Detailed error messages and stack traces

## Running Tests

### 1. Start Services
```bash
./start_services.sh
```

This will:
- Activate virtual environment
- Start Registry (port 8000)
- Start Orchestrator (port 8100)
- Start all agents (ports 8001-8004)

### 2. Run Tests
```bash
source venv/bin/activate
python test_distributed_system.py
```

## Expected Test 5 Output

The workflow test will now show:

```
Test 5: Workflow Execution
------------------------------------------------------------
Executing workflow...
Task: Analyze Python code for a simple function and explain what it does

✓ Workflow executed successfully

  Workflow ID: test-workflow-1770289899.865652
  Status: completed
  Steps completed: 2/2

  📋 Execution Plan:
     Reasoning: <LLM reasoning for the plan>
     Steps planned: 2
       1. Analyze the Python code structure
          Capability: analyze_python_code
       2. Explain what the code does
          Capability: explain_code

  �� Execution Results:
     Step 1: analyze_python_code
       Agent: CodeAnalyzer
       Result: The code defines a simple function...
     Step 2: explain_code
       Agent: CodeAnalyzer
       Result: This function returns the string 'world'...

  📝 Execution Log:
     ✓ Discovery: Found 4 agents
     ✓ Planning: Generated 2 steps
     ✓ Step 1: Completed by CodeAnalyzer
     ✓ Step 2: Completed by CodeAnalyzer
```

## Orchestrator Logs

The orchestrator will show detailed logs:

```
================================================================================
🚀 WORKFLOW EXECUTION STARTED
================================================================================
Workflow ID: test-workflow-1770289899.865652
Task: Analyze Python code for a simple function and explain what it does

📋 STEP 1: Discovering available agents...
   Found 4 registered agents
   - CodeAnalyzer (specialized)
     ✓ analyze_python_code: Analyze Python code structure and logic
     ✓ explain_code: Explain what code does in plain language
   - DataProcessor (specialized)
     ✓ transform_data: Transform data formats
   - ResearchAgent (specialized)
     ✓ answer_question: Answer questions using research

   Available capabilities: analyze_python_code, explain_code, transform_data, answer_question

🧠 STEP 2: Generating execution plan using LLM...
   Model: anthropic.claude-3-5-sonnet-20241022-v2:0
   Calling Bedrock with model: anthropic.claude-3-5-sonnet-20241022-v2:0
   LLM Response length: 456 characters
   ✓ Valid plan with 2 steps
   Generated plan with 2 steps
   Reasoning: <reasoning>

⚙️  STEP 3: Executing plan...

   📌 Step 1: Analyze the Python code structure
      Capability: analyze_python_code
      Parameters: {"code": "def hello(): return 'world'"}
      Agent: CodeAnalyzer
      Endpoint: http://localhost:8001
      🔄 Sending task to agent...
      ✅ Step 1 completed successfully
      Result preview: The code defines a simple function...

   📌 Step 2: Explain what the code does
      Capability: explain_code
      Parameters: {"code": "def hello(): return 'world'"}
      Agent: CodeAnalyzer
      Endpoint: http://localhost:8001
      🔄 Sending task to agent...
      ✅ Step 2 completed successfully
      Result preview: This function returns the string 'world'...

================================================================================
✅ WORKFLOW COMPLETED
================================================================================
Steps completed: 2/2
Execution time: 2026-02-05T11:10:00 to 2026-02-05T11:10:15
```

## Troubleshooting

### If Steps Show 0/N Completed

1. **Check AWS Credentials**: Ensure Bedrock has valid credentials
2. **Check LLM Response**: Look for parsing errors in orchestrator logs
3. **Check Agent Availability**: Ensure agents are registered and responding
4. **Check Capability Matching**: LLM might generate invalid capability names

### If LLM Planning Fails

The system will automatically fall back to a default plan based on:
- Task keywords (code, analyze, data, research)
- Available capabilities
- Simple parameter matching

### Common Issues

1. **Port Already in Use**: Stop existing services with `./stop_services.sh`
2. **AWS Credentials Invalid**: Check `.env` files or `~/.aws/credentials`
3. **No Agents Available**: Wait a few seconds after starting services for registration

## Architecture Summary

```
User Query → Test Script
    ↓
Orchestrator (port 8100)
    ↓
1. Query Registry → Get Available Agents & Capabilities
2. Call Bedrock LLM → Generate Execution Plan
3. Execute Plan → Send Tasks to Agents via A2A Protocol
    ↓
Agents (ports 8001-8004)
    ↓
    Each agent:
    - Receives task via A2A
    - Calls Bedrock for LLM reasoning
    - Returns result via A2A
    ↓
Orchestrator → Aggregates Results
    ↓
Return to User
```

## Next Steps

1. Run `./start_services.sh` to start all services
2. Run `python test_distributed_system.py` to see detailed logs
3. Check orchestrator terminal for step-by-step execution details
4. Review test output for execution plan and results

All fixes ensure:
- ✅ Detailed logging at every step
- ✅ Proper AWS credential handling
- ✅ LLM response validation
- ✅ Fallback mechanisms
- ✅ Clear error messages
- ✅ Complete workflow visibility

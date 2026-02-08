# Interactive Workflow Guide

## Overview

The A2A system now supports **collaborative human-AI workflows** where agents can request user input during execution without losing context or breaking the flow.

## How It Works

### 1. **Agent Requests Input**

When an agent needs additional information, it returns a special response:

```python
{
    "status": "user_input_required",
    "interaction_request": {
        "question": "Which data format should I use?",
        "input_type": "single_choice",  # or "text", "multiple_choice", "confirmation"
        "options": ["CSV", "JSON", "XML"],
        "context": "The API supports multiple formats",
        "placeholder": "Enter your choice..."  # for text input
    }
}
```

### 2. **Orchestrator Pauses Workflow**

The orchestrator:
- Detects the `user_input_required` status
- Saves the workflow state to the database
- Creates an interaction request via InteractionManager
- Notifies WebSocket clients
- Returns immediately with status `waiting_for_input`

### 3. **User Responds via WebSocket**

The HTML client:
- Shows the question in the UI
- Presents options (if applicable)
- Sends user response back via WebSocket:

```javascript
{
    "type": "user_response",
    "request_id": "abc-123",
    "response": "JSON"
}
```

### 4. **Workflow Resumes**

The WebSocketMessageHandler:
- Receives the user response
- Validates and stores it via InteractionManager
- Calls `executor.resume_workflow(workflow_id)`
- The workflow continues from where it paused

### 5. **Agent Receives Context**

The agent gets the user's response and continues:

```python
# Agent receives the user's response in context
user_input = context.get("user_response")
# Continue processing with user input
```

## Architecture Components

### Orchestrator (`app.py`)
- Detects `user_input_required` in agent responses
- Creates interaction requests
- Pauses workflow execution
- Broadcasts to WebSocket clients

### InteractionManager (`interaction.py`)
- Manages interaction lifecycle
- Stores requests in database
- Validates responses
- Tracks conversation history

### WorkflowExecutor (`executor.py`)
- Resumes paused workflows
- Injects user responses into agent context
- Continues execution from paused step

### WebSocketMessageHandler (`websocket_handler.py`)
- Handles real-time communication
- Broadcasts workflow events
- Receives user responses
- Triggers workflow resumption

### Database (`database.py`)
- Persists workflow state
- Stores interaction requests/responses
- Maintains conversation history

## Example Use Cases

### 1. Research Agent Needs Clarification

```python
# Task: "Research our top 5 competitors"
# Agent Response:
{
    "status": "user_input_required",
    "interaction_request": {
        "question": "Which industry should I focus on?",
        "input_type": "text",
        "context": "Multiple industries detected in company profile"
    }
}
```

### 2. Data Processor Needs Format Choice

```python
# Task: "Export the analysis results"
# Agent Response:
{
    "status": "user_input_required",
    "interaction_request": {
        "question": "Select export format",
        "input_type": "single_choice",
        "options": ["CSV", "JSON", "Excel", "PDF"]
    }
}
```

### 3. Code Analyzer Needs Confirmation

```python
# Task: "Refactor this code"
# Agent Response:
{
    "status": "user_input_required",
    "interaction_request": {
        "question": "Should I proceed with breaking changes?",
        "input_type": "confirmation",
        "context": "Refactoring will change public API"
    }
}
```

## Testing the Interactive Workflow

### Using the HTML Client

1. **Start Services**:
   ```bash
   ./start_services.sh
   ```

2. **Open WebSocket Test Client**:
   ```bash
   open services/orchestrator/websocket_test_client.html
   ```

3. **Connect**:
   - Enter a workflow ID or leave empty for new
   - Click "Connect"

4. **Submit Task**:
   ```
   Research our top 5 competitors in the cloud computing space and 
   provide a detailed analysis including their market share and key strategies
   ```

5. **Respond to Questions**:
   - When the agent asks for clarification, the UI will show the question
   - Select/enter your response
   - The workflow automatically resumes

### Example Interactive Tasks

#### Task 1: Research with Clarification
```
Research our top 5 competitors and provide a detailed analysis
```
**Agent will ask**: "Which industry should I focus on?"

#### Task 2: Data Analysis with Format Choice
```
Analyze sales data and export the results
```
**Agent will ask**: "Which format should I use for the export?"

#### Task 3: Code Analysis with Confirmation
```
Analyze the authentication module and suggest security improvements
```
**Agent will ask**: "Should I include refactoring recommendations that may require breaking changes?"

## WebSocket Message Types

### Client to Server

- `get_status`: Request workflow status
- `user_response`: Submit user input
- `cancel_workflow`: Cancel workflow
- `get_conversation`: Get conversation history

### Server to Client

- `connection_established`: Connection confirmed
- `workflow_status`: Current workflow state
- `step_started`: Step execution started
- `step_completed`: Step completed successfully
- `step_failed`: Step failed
- `user_input_required`: Agent needs user input
- `response_received`: User response acknowledged
- `workflow_resuming`: Workflow resuming after input
- `workflow_completed`: Workflow finished
- `error`: Error occurred

## State Management

### Workflow States

- `planning`: Planning execution steps
- `running`: Executing steps
- `waiting_for_input`: Paused, awaiting user response
- `completed`: Successfully finished
- `failed`: Execution failed
- `cancelled`: User cancelled

### Interaction States

- `pending`: Waiting for user response
- `answered`: User provided response
- `timeout`: User didn't respond in time
- `cancelled`: Interaction cancelled

## Best Practices

### For Agent Developers

1. **Be Specific**: Ask clear, specific questions
2. **Provide Context**: Explain why you need the information
3. **Offer Options**: When applicable, provide choices
4. **Set Reasonable Expectations**: Don't ask too many questions
5. **Handle Timeouts**: Have a default behavior if user doesn't respond

### For Workflow Designers

1. **Minimize Interruptions**: Only ask when necessary
2. **Group Questions**: If multiple inputs needed, ask together
3. **Provide Defaults**: Suggest sensible defaults
4. **Show Progress**: Keep user informed of workflow state
5. **Allow Cancellation**: Let users abort if needed

## Troubleshooting

### Workflow Not Pausing

**Check**:
- Agent returns `status: "user_input_required"`
- InteractionManager is initialized
- Database is accessible

### WebSocket Not Receiving Messages

**Check**:
- WebSocket connection established
- Workflow ID matches
- ConnectionManager has active connections

### Workflow Not Resuming

**Check**:
- User response includes correct `request_id`
- Response passes validation
- WorkflowExecutor has workflow state in database

## Future Enhancements

- [ ] Multiple user interactions per step
- [ ] Interaction timeouts with fallback behavior
- [ ] Rich media in questions (images, code snippets)
- [ ] Multi-user collaboration (approvals, voting)
- [ ] Interaction history and replay
- [ ] Smart defaults based on user history

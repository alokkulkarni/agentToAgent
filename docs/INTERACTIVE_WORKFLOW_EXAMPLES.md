# Interactive Workflow Examples

This document provides example tasks that demonstrate the A2A system's interactive capabilities where agents can request additional information from users during workflow execution.

## 🎯 Example Tasks

### 1. **Code Analysis with Clarification** (Currently Supported)

**Task Description:**
```
Analyze the authentication module in our codebase and suggest security improvements
```

**What Happens:**
1. **CodeAnalyzer** starts analyzing the code
2. Finds multiple authentication files
3. **Requests user input**: "Which authentication module should I focus on? Options: OAuth, JWT, SAML"
4. User selects "JWT"
5. Agent continues with detailed JWT analysis
6. Provides security recommendations

**WebSocket Test:**
```javascript
{
  "task_description": "Analyze the authentication module in our codebase and suggest security improvements",
  "workflow_id": "code_analysis_001"
}
```

---

### 2. **Data Analysis with Context** (Currently Supported)

**Task Description:**
```
Analyze sales data and provide insights
```

**What Happens:**
1. **DataProcessor** receives the task
2. **Requests clarification**: "What time period should I analyze? Options: Last Month, Last Quarter, Last Year, Custom"
3. User selects "Last Quarter"
4. Agent asks: "What metrics are most important? Options: Revenue Growth, Customer Acquisition, Churn Rate, All"
5. User selects "Revenue Growth"
6. Agent performs focused analysis
7. Provides targeted insights

---

### 3. **Research with Iterative Refinement** (Currently Supported)

**Task Description:**
```
Research the latest trends in artificial intelligence
```

**What Happens:**
1. **ResearchAgent** begins broad research
2. Finds multiple AI subdomains
3. **Requests focus**: "Which AI area interests you most? Options: NLP, Computer Vision, Reinforcement Learning, Generative AI"
4. User selects "Generative AI"
5. Agent asks: "What aspect? Options: Models & Architectures, Applications, Ethics & Safety, Business Impact"
6. User selects "Applications"
7. Agent provides detailed research on generative AI applications

---

### 4. **Multi-Step Math with Validation** (Math Agent Example)

**Task Description:**
```
Calculate the compound interest for my investment
```

**What Happens:**
1. **MathAgent** receives the task
2. **Requests initial amount**: "What is your initial investment amount?" (text input)
3. User enters: "10000"
4. **Requests interest rate**: "What is the annual interest rate (%)?" (text input)
5. User enters: "5.5"
6. **Requests time period**: "Investment duration in years?" (text input)
7. User enters: "10"
8. **Requests compounding frequency**: "How often is interest compounded? Options: Annually, Semi-annually, Quarterly, Monthly"
9. User selects "Quarterly"
10. Agent calculates and provides:
    - Final amount
    - Total interest earned
    - Year-by-year breakdown

---

### 5. **Report Generation with Preferences** (Current System)

**Task Description:**
```
Generate a comprehensive report on Q4 performance
```

**What Happens:**
1. **DataProcessor** gathers Q4 data
2. **Requests report format**: "How detailed should the report be? Options: Executive Summary, Detailed Analysis, Full Report"
3. User selects "Detailed Analysis"
4. **Requests sections**: "Which sections to include? Options: Financial, Operations, Sales, Marketing, All"
5. User selects multiple: ["Financial", "Sales"]
6. Agent generates focused report
7. **Asks for export format**: "Export as? Options: PDF, Excel, PowerPoint, JSON"
8. User selects "PDF"
9. Agent generates and delivers formatted report

---

## 🧪 Testing with WebSocket Client

### Step 1: Start Services
```bash
./start_services.sh
```

### Step 2: Open WebSocket Client
Open `websocket_test_client.html` in your browser at:
```
/Users/alokkulkarni/Documents/Development/agentToAgent/services/orchestrator/websocket_test_client.html
```

### Step 3: Connect
1. Enter a workflow ID (e.g., `test_interactive_001`)
2. Click **Connect**
3. Wait for confirmation: "✓ Connected to workflow"

### Step 4: Submit Workflow
1. Enter one of the task descriptions above
2. Click **Execute Workflow**
3. Watch the real-time progress in the Messages panel

### Step 5: Respond to Interactions
When an agent requests input:
1. A blue interaction box appears
2. Read the question and reasoning
3. Select an option or enter text
4. Click to submit response
5. Workflow automatically resumes

---

## 📊 Expected Message Flow

### Successful Interactive Workflow

```
[09:30:15] ✓ Connected to workflow: test_interactive_001
[09:30:16] Submitting workflow: Analyze sales data and provide insights
[09:30:16] ✓ Workflow submitted: test_interactive_001
[09:30:17] ▶️ Step 1/2: Gather and process sales data
[09:30:19] ❓ User input required - please respond below

    Question: What time period should I analyze?
    Options: [Last Month] [Last Quarter] [Last Year] [Custom]

[09:30:25] ✓ Submitted response: Last Quarter
[09:30:25] ✓ Response received, workflow resuming...
[09:30:25] 🔄 Workflow resuming...
[09:30:26] ✅ Step 1 completed: Gather and process sales data
[09:30:26]    Result: {"period": "Q4", "records": 15234, ...}
[09:30:26] ▶️ Step 2/2: Analyze data and generate insights
[09:30:30] ✅ Step 2 completed: Analyze data and generate insights
[09:30:30]    Result: {"growth": 23.5%, "insights": [...]}
[09:30:30] 🎉 Workflow completed!
[09:30:30]    Summary: Successfully analyzed Q4 sales data with 23.5% growth
```

---

## 🔧 Creating Custom Interactive Tasks

### Agent Side (Python)

```python
from interaction import InteractionRequest

# In your agent's handle_task method:
async def handle_task(self, task: TaskRequest) -> TaskResponse:
    # Check if we need user input
    if self._needs_clarification(task):
        # Request user input via interaction manager
        interaction = InteractionRequest(
            workflow_id=task.context.get("workflow_id"),
            agent_id=self.agent_id,
            question="Which option should I use?",
            input_type="single_choice",
            options=["Option A", "Option B", "Option C"],
            reasoning="I need to know which approach to take",
            context=task.dict()
        )
        
        # This will pause workflow and wait for user response
        response = await self.interaction_manager.request_input(interaction)
        
        # Continue with user's choice
        selected_option = response["response"]
        # ... process with selected_option
    
    # Normal processing
    result = self._process(task)
    return TaskResponse(status=TaskStatus.COMPLETED, result=result)
```

### Client Side (JavaScript)

```javascript
// The WebSocket client automatically handles interaction requests
// When server sends "user_input_required" message, it displays the interaction UI
// User responses are automatically sent back via WebSocket

// You can also programmatically respond:
ws.send(JSON.stringify({
    type: 'user_response',
    request_id: 'req_123',
    response: 'Option B',
    additional_context: {
        confidence: 'high',
        notes: 'This is the best choice because...'
    }
}));
```

---

## 🎯 Best Practices

### For Agents
1. **Be Specific**: Ask clear, focused questions
2. **Provide Context**: Explain WHY you need the information
3. **Offer Options**: When possible, provide choices rather than open text
4. **Set Defaults**: Have fallback behavior if user doesn't respond
5. **Validate Input**: Check user responses before continuing

### For Users
1. **Stay Connected**: Keep WebSocket connection open during workflow
2. **Respond Promptly**: Agents may timeout if no response
3. **Be Clear**: Provide complete information to avoid follow-up questions
4. **Use Context**: Review conversation history if needed

---

## 🚀 Advanced Features

### Multiple Choice vs Text Input

```python
# Single choice (radio buttons)
InteractionRequest(
    question="Select deployment environment",
    input_type="single_choice",
    options=["Development", "Staging", "Production"]
)

# Text input (free form)
InteractionRequest(
    question="Enter the server hostname",
    input_type="text",
    placeholder="e.g., api.example.com"
)
```

### Conditional Follow-ups

```python
# Agent can ask follow-up questions based on previous answers
first_response = await request_input("What type of analysis?")

if first_response == "Financial":
    second_response = await request_input("Which financial metric?")
elif first_response == "Operations":
    second_response = await request_input("Which operational metric?")
```

### Conversation History

```javascript
// Request full conversation history
ws.send(JSON.stringify({type: 'get_conversation'}));

// Server responds with:
{
    type: 'conversation_history',
    history: [
        {role: 'agent', message: 'What should I analyze?'},
        {role: 'user', message: 'Sales data'},
        {role: 'agent', message: 'Which time period?'},
        {role: 'user', message: 'Last quarter'}
    ]
}
```

---

## 📝 Notes

- **State Persistence**: Workflow state is preserved in database during user interaction
- **Timeout Handling**: Workflows can timeout after extended inactivity (configurable)
- **Multi-User**: Multiple WebSocket connections can observe same workflow
- **REST Fallback**: Can respond via REST API if WebSocket unavailable
- **Error Recovery**: Failed interactions can be retried or skipped

---

## 🔗 Related Documentation

- [INTERACTIVE_WORKFLOW_IMPLEMENTATION.md](./INTERACTIVE_WORKFLOW_IMPLEMENTATION.md) - Technical implementation details
- [AGENTS_UPGRADED_SUMMARY.md](./AGENTS_UPGRADED_SUMMARY.md) - Agent upgrade guide
- [WEBSOCKET_QUICK_START.md](./WEBSOCKET_QUICK_START.md) - WebSocket setup guide

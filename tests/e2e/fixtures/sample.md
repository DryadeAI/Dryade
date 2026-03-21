# Dryade Workflow Execution Guide

## Overview

This guide covers workflow execution in the Dryade multi-agent system. Workflows
enable complex task orchestration across multiple agents with automatic flow
control and state management.

## Core Concepts

### Workflow Definition

A workflow consists of:

- **Nodes**: Individual processing steps (agents, tasks, routers)
- **Edges**: Connections defining execution flow
- **Inputs**: Parameters passed at execution time
- **Outputs**: Results produced by the workflow

### Agent Types

Dryade supports several agent types for workflow execution:

1. **Research Agent** - Gathers information from various sources
2. **Writer Agent** - Produces written content based on inputs
3. **Analyst Agent** - Processes data and generates insights
4. **Router Agent** - Directs flow based on conditions

## Creating Workflows

### Basic Structure

```json
{
  "version": "1.0.0",
  "nodes": [
    {"id": "start-1", "type": "start"},
    {"id": "task-1", "type": "task", "agent": "research"},
    {"id": "end-1", "type": "end"}
  ],
  "edges": [
    {"source": "start-1", "target": "task-1"},
    {"source": "task-1", "target": "end-1"}
  ]
}
```

### Node Configuration

Each node requires specific configuration:

```json
{
  "id": "research-task",
  "type": "task",
  "agent": "research",
  "config": {
    "goal": "Research market trends",
    "backstory": "Expert market analyst",
    "tools": ["web_search", "data_analysis"]
  }
}
```

## Execution Flow

### Starting Execution

Initiate workflow execution via the API:

```bash
POST /api/workflows/{id}/execute
Content-Type: application/json

{
  "inputs": {"query": "AI market trends 2024"},
  "user_id": "user_123"
}
```

### Flow Control

The execution engine manages:

- Task scheduling and dependencies
- Agent selection and initialization
- State persistence across steps
- Error handling and retries

### Monitoring Progress

Track execution through Server-Sent Events (SSE):

```javascript
const eventSource = new EventSource('/api/workflows/1/execute/stream');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Progress:', data.type, data.payload);
};
```

## Advanced Features

### Conditional Routing

Router nodes enable dynamic flow control:

```json
{
  "id": "router-1",
  "type": "router",
  "conditions": [
    {"if": "confidence > 0.8", "goto": "high-confidence-path"},
    {"if": "confidence <= 0.8", "goto": "review-path"}
  ]
}
```

### Parallel Execution

Multiple branches can execute concurrently:

```json
{
  "edges": [
    {"source": "start", "target": "branch-a"},
    {"source": "start", "target": "branch-b"},
    {"source": "branch-a", "target": "merge"},
    {"source": "branch-b", "target": "merge"}
  ]
}
```

### Error Handling

Configure retry policies and fallbacks:

```json
{
  "error_handling": {
    "max_retries": 3,
    "retry_delay": 1000,
    "fallback_node": "error-handler"
  }
}
```

## Best Practices

### Workflow Design

1. Keep workflows modular and focused
2. Use descriptive node IDs for debugging
3. Implement proper error handling at each step
4. Test workflows in staging before production

### Agent Configuration

1. Provide clear, specific goals for each agent
2. Assign appropriate tools based on task requirements
3. Configure backstories to guide agent behavior
4. Set reasonable token limits for responses

### Execution Monitoring

1. Subscribe to SSE streams for real-time updates
2. Log execution metrics for performance analysis
3. Set up alerts for failed workflows
4. Review execution history regularly

## Troubleshooting

### Common Issues

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Workflow stuck | Agent timeout | Check LLM service connectivity |
| Invalid output | Missing context | Review agent backstory and tools |
| Route failure | Bad condition | Validate router expressions |

### Debugging Tips

1. Enable verbose logging during development
2. Check the execution trace for failed nodes
3. Verify input data format matches expectations
4. Test individual agents before combining

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /workflows | Create workflow |
| GET | /workflows/{id} | Get workflow details |
| POST | /workflows/{id}/execute | Start execution |
| GET | /workflows/{id}/status | Check status |

For more information, see the complete API documentation.

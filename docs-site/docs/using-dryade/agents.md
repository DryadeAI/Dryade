---
title: Agents
sidebar_position: 2
---

# Agents

Agents are AI assistants that can autonomously use tools, access knowledge, and complete multi-step tasks. While chat gives you a direct conversation with an LLM, agents add planning, tool access, and persistence.

![Agents panel showing agent cards with capabilities, tool counts, and the ReAct execution loop](/img/screenshots/agents-panel.png)

## What Agents Do

An agent in Dryade is an AI that can:

- **Use tools** -- Call MCP servers to read files, search the web, interact with APIs, and more
- **Plan and execute** -- Break complex requests into steps and work through them
- **Access knowledge** -- Query your uploaded documents for grounded, accurate responses
- **Maintain context** -- Remember relevant information across interactions
- **Recover from errors** -- Detect when something goes wrong and try alternative approaches

## Built-in Agents

Dryade comes with a default agent configuration that is ready to use. The default agent has access to all enabled MCP tools and the knowledge base.

## Using Agents in Conversations

To interact with an agent:

1. Go to **Chat** in the sidebar
2. Start a new conversation
3. Select your agent from the model/agent selector
4. Type your request and send

The agent processes your request by reasoning about what to do, selecting appropriate tools, executing them, and synthesizing the results into a response. You see each step as it happens.

### Example Interaction

**You:** "Summarize the changes in the last 5 Git commits and identify any breaking changes."

**Agent:**
1. Calls `git_log` to get the last 5 commits
2. Calls `git_diff` for each commit to see the changes
3. Analyzes the diffs for breaking patterns (API changes, removed exports, schema changes)
4. Returns a structured summary with identified risks

## Agent Capabilities

### Tool Calling

Agents select and call tools based on the task. The tool selection is automatic -- you describe what you want, and the agent figures out which tools to use.

Available tools depend on which [MCP servers](/using-dryade/mcp) you have enabled. Common capabilities include:

| Capability | MCP Server | What it does |
|-----------|------------|--------------|
| File access | Filesystem | Read, write, and manage files |
| Git operations | Git | Status, diff, log, commit, branch |
| Browser automation | Playwright | Navigate, screenshot, click, fill forms |
| GitHub integration | GitHub | Issues, PRs, repos, file contents |
| Document processing | PDF Reader | Extract text and tables from PDFs |

### Multi-Step Reasoning

For complex tasks, agents break the work into steps:

1. **Analyze** the request to understand what is needed
2. **Plan** the sequence of actions
3. **Execute** each step, using tools as needed
4. **Observe** the results and decide what to do next
5. **Synthesize** a final response

You see each step in the conversation, giving you visibility into the agent's reasoning process.

### Knowledge Base Integration

Agents can query your [Knowledge Base](/using-dryade/knowledge) to ground responses in your actual data. When you ask a question that relates to your uploaded documents, the agent retrieves relevant context before generating its answer.

This is particularly useful for:

- Answering questions about your codebase or documentation
- Referencing company policies or procedures
- Finding information across multiple uploaded documents

### Error Recovery

When a tool call fails or produces unexpected results, agents can:

- Retry with different parameters
- Try an alternative approach
- Ask you for clarification
- Report what went wrong and suggest next steps

## Creating Custom Agents

To create an agent tailored to your needs:

1. Go to **Agents** in the sidebar
2. Click **Create Agent**
3. Configure the agent:
   - **Name** -- A descriptive name for the agent
   - **Description** -- What the agent is designed to do
   - **System prompt** -- Instructions that guide the agent's behavior
   - **Tools** -- Which MCP servers the agent can access
4. Save the agent

### System Prompt Tips

The system prompt shapes how the agent behaves. Good system prompts:

- Define the agent's role ("You are a code reviewer who focuses on security...")
- Set boundaries ("Only suggest changes, never modify files directly")
- Specify output format ("Always include a confidence rating from 1-5")
- Provide domain context ("This project uses FastAPI and SQLAlchemy...")

## Tips

- **Match the agent to the task.** Use the default agent for general tasks. Create specialized agents for recurring workflows where specific instructions help.
- **Enable relevant MCP servers.** Agents are most useful when they have access to the right tools. A code review agent needs Git and filesystem access; a research agent benefits from web browsing.
- **Provide context upfront.** The more context you give in your initial message, the better the agent can plan its approach.
- **Review multi-step results.** For complex tasks, check the intermediate results in the conversation to make sure the agent is on the right track.

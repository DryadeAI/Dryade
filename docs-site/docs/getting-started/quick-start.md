---
title: Quick Start
sidebar_position: 3
---

# Quick Start

Get from zero to your first AI conversation in under 5 minutes.

## Step 1: Install Dryade

If you have not installed Dryade yet, the quickest path is Docker:

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
cp .env.example .env
docker-compose up -d
```

For detailed installation options, see the [Installation](/getting-started/installation) page.

## Step 2: Open the Workbench

Once Dryade is running, open your browser to:

```
http://localhost:3000
```

You will see the Dryade Workbench -- your central workspace for conversations, agents, workflows, and knowledge management.

## Step 3: Create Your Account

On your first visit, click **Sign Up** to create an account. Enter your email address and choose a password. After registration, you will be signed in automatically.

## Step 4: Complete the Onboarding Wizard

The onboarding wizard appears on your first login. It walks you through:

1. **Select an LLM provider** -- Choose from OpenAI, Anthropic, Google, a local vLLM endpoint, or other supported providers
2. **Enter your API key** -- Paste your provider API key
3. **Test the connection** -- Dryade verifies that your key works and the provider is reachable
4. **Optional: Configure MCP servers** -- Enable tool integrations like filesystem access, Git, or browser automation

You can skip optional steps and configure them later through [Settings](/using-dryade/settings).

For a detailed walkthrough, see the [Onboarding Guide](/getting-started/onboarding-guide).

## Step 5: Start a Conversation

After completing the wizard, you land on the Chat page. Here is how to have your first conversation:

1. Click **New Chat** in the sidebar (or use the shortcut)
2. Type your message in the input field at the bottom
3. Press **Enter** or click **Send**
4. Watch the AI response stream in real time

Try something like:

> "Explain what Dryade can do for me in three bullet points."

The AI will respond using whichever LLM provider you configured. You can see which model is active in the chat header.

## Step 6: Create Your First Agent

Agents are AI assistants with access to tools and context. To create one:

1. Go to **Agents** in the sidebar
2. Click **Create Agent**
3. Give your agent a name and description
4. Select which tools the agent can use (MCP servers, built-in functions)
5. Save and start a conversation with your agent

Agents can call tools, search your knowledge base, and perform multi-step tasks autonomously.

## What You Can Do Next

Now that you are up and running, explore these features:

| Feature | What it does | Learn more |
|---------|-------------|------------|
| **Chat** | Multi-model conversations with streaming, tool use, and code | [Chat & Conversations](/using-dryade/chat) |
| **Agents** | Autonomous AI assistants with tool access | [Agents](/using-dryade/agents) |
| **Workflows** | Visual automation builder with drag-and-drop | [Visual Workflow Builder](/using-dryade/workflows) |
| **Knowledge** | Upload documents for AI-powered retrieval | [Knowledge Base & RAG](/using-dryade/knowledge) |
| **MCP** | Connect external tool servers | [MCP Servers](/using-dryade/mcp) |
| **Settings** | Configure providers, keys, and preferences | [Settings](/using-dryade/settings) |

## Tips for Getting Started

- **Switch models on the fly.** Use the model selector in the chat header to try different LLMs without leaving your conversation.
- **Enable MCP servers for richer interactions.** Tools like filesystem access and Git operations make agents significantly more capable.
- **Use the knowledge base for grounding.** Upload relevant documents so the AI can reference your actual data instead of relying on its training.
- **Build workflows for repetitive tasks.** If you find yourself doing the same multi-step process, turn it into a visual workflow.

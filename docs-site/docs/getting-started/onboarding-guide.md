---
title: Onboarding Guide
sidebar_position: 4
---

# Onboarding Guide

When you first sign in to Dryade, the onboarding wizard walks you through initial configuration. This guide explains each step in detail so you know what to expect and how to make the best choices.

![Onboarding wizard showing provider selection step with OpenAI, Anthropic, Google, and vLLM options](/img/screenshots/workspace-dashboard.png)

## Overview

The onboarding wizard runs once after your first login. It helps you:

- Connect an LLM provider so AI features work
- Validate your API key with a live connection test
- Optionally configure MCP tool servers
- Optionally run a test conversation

You can skip any optional step and return to it later through [Settings](/using-dryade/settings).

## Step 1: Choose an LLM Provider

Dryade supports multiple LLM providers. Select the one you want to use as your primary model:

| Provider | Models | What you need |
|----------|--------|---------------|
| **OpenAI** | GPT-4o, GPT-4, GPT-3.5 Turbo | API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | Claude 4, Claude 3.5 Sonnet | API key from [console.anthropic.com](https://console.anthropic.com/) |
| **Google** | Gemini 2.5 Pro, Gemini 2.5 Flash | API key from [aistudio.google.com](https://aistudio.google.com/) |
| **Local (vLLM)** | Any model served by vLLM | A running vLLM endpoint URL |
| **Other OpenAI-compatible** | Varies | Base URL + API key |

:::tip
You can add more providers later. The onboarding wizard sets up your primary provider -- you are not locked in.
:::

### Getting an API Key

**OpenAI:**
1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Click "Create new secret key"
3. Copy the key (it starts with `sk-`)

**Anthropic:**
1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Navigate to API Keys
3. Click "Create Key"
4. Copy the key (it starts with `sk-ant-`)

**Google:**
1. Go to [aistudio.google.com](https://aistudio.google.com/)
2. Click "Get API Key"
3. Create a key for your project

**Local vLLM:**
No API key needed. Enter the URL where your vLLM server is running (for example, `http://localhost:8080/v1`).

## Step 2: Enter Your API Key

Paste your API key into the input field. The key is stored securely on your Dryade instance -- it is never sent anywhere except to the LLM provider you selected.

For local vLLM endpoints, enter the base URL instead.

:::note Security
Your API keys are stored encrypted in your Dryade database. They are only used to authenticate requests to your chosen LLM provider.
:::

## Step 3: Test the Connection

Click **Test Connection** to verify that Dryade can reach your provider. The wizard sends a small test request and checks:

- The API key is valid and has the right permissions
- The provider endpoint is reachable from your server
- At least one model is available

**If the test succeeds**, you will see a green confirmation with the list of available models.

**If the test fails**, the wizard shows the error message. Common issues:

| Error | Cause | Fix |
|-------|-------|-----|
| "Invalid API key" | Key is incorrect or expired | Double-check the key, generate a new one if needed |
| "Connection refused" | Provider endpoint unreachable | Check your network, firewall, or proxy settings |
| "Rate limited" | Too many requests | Wait a moment and try again |
| "Insufficient permissions" | Key lacks required scopes | Create a new key with full model access |

## Step 4: Configure MCP Servers (Optional)

MCP (Model Context Protocol) servers provide tools that AI can use during conversations. This step lets you enable the ones you want:

| Server | What it does | Needs credentials? |
|--------|-------------|-------------------|
| **Filesystem** | Read and write files in a sandboxed directory | No |
| **Git** | Git operations (status, diff, log, commit) | No |
| **Memory** | Persistent knowledge graph for agent memory | No |
| **Playwright** | Browser automation and screenshots | No |
| **GitHub** | GitHub API (issues, PRs, repos) | Yes -- GitHub token |
| **Linear** | Linear issue tracking | Yes -- Linear API key |
| **PDF Reader** | Extract text and tables from PDFs | No |
| **Context7** | Library documentation lookup | No |

You can enable servers that need no credentials immediately. For servers that require API keys (GitHub, Linear), enter the keys when prompted.

For full details on each MCP server, see the [MCP Servers](/using-dryade/mcp) page.

:::tip
You do not need to enable any MCP servers right now. Basic chat and agent features work without them. Enable MCP servers when you want AI to interact with external tools.
:::

## Step 5: Test Conversation (Optional)

The wizard offers to run a quick test conversation to confirm everything is working end-to-end. This sends a simple prompt to your configured LLM and displays the response.

If the test conversation works, your setup is complete.

## What Happens If You Skip Steps

Every step after the LLM provider setup is optional. Here is what each skip means:

| Skipped Step | Effect | How to set up later |
|-------------|--------|-------------------|
| MCP servers | AI cannot use external tools (file access, Git, etc.) | Settings > MCP Servers |
| Test conversation | No verification that everything works | Just start a chat manually |

The only step you cannot skip is LLM provider configuration -- without at least one provider, AI features will not work.

## After the Wizard

Once you complete the wizard, you land on the Chat page ready to go. From here you can:

- **Start chatting** with your configured LLM
- **Create agents** with tool access for more complex tasks
- **Build workflows** to automate multi-step processes
- **Upload documents** to the knowledge base for grounded responses

To change any configuration you set during onboarding, go to [Settings](/using-dryade/settings). Everything is editable after initial setup.

## Returning to Configuration

If you need to change your LLM provider, add a new one, or adjust MCP server settings after onboarding:

1. Click **Settings** in the sidebar
2. Navigate to the relevant section:
   - **LLM Providers** -- Add, edit, or remove provider configurations
   - **MCP Servers** -- Enable, disable, or configure tool servers
   - **Preferences** -- Theme, language, and display settings

See the [Settings](/using-dryade/settings) page for a full reference.

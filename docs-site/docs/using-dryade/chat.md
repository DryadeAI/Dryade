---
title: "Chat & Conversations"
sidebar_position: 1
---

# Chat & Conversations

The Chat page is where you interact with AI models in real time. Start conversations, switch between models, use tools, and review your history -- all from a single interface.

![Chat interface showing conversation with code generation, tool calls, and the model selector](/img/screenshots/workspace-chat.png)

## Starting a Conversation

1. Click **New Chat** in the sidebar or use the chat page
2. Type your message in the input field at the bottom of the screen
3. Press **Enter** or click the **Send** button
4. The AI response streams in real time as it is generated

Each conversation is saved automatically. You can return to any previous conversation from the sidebar.

## Multi-Model Support

Dryade supports multiple LLM providers simultaneously. You can switch between models without leaving your conversation:

- **Model selector** -- Use the dropdown in the chat header to pick a different model
- **Mid-conversation switching** -- Change models at any point; the conversation history carries over
- **Provider variety** -- Use OpenAI, Anthropic, Google, local vLLM models, or any OpenAI-compatible endpoint

This is useful for comparing how different models handle the same question, or switching to a faster model for simple tasks.

## Streaming Responses

Responses stream in real time using Server-Sent Events (SSE). You see each token as the model generates it, rather than waiting for the full response.

- **Live typing effect** -- Text appears progressively as the model thinks
- **Early reading** -- Start reading the response before it finishes
- **Cancel** -- Stop generation at any time if the response is going in the wrong direction

## Tool Use

When MCP servers are enabled, the AI can use tools during conversations. You will see tool calls and their results inline:

1. The AI decides it needs to use a tool (for example, reading a file or searching the web)
2. The tool call appears in the conversation with a brief description
3. The tool executes and returns results
4. The AI incorporates the results into its response

Tool use is automatic -- you do not need to tell the AI which tools to use. It selects the right tool based on the context of your request.

### Common Tool-Enabled Tasks

- **File operations** -- Read, write, and organize files through the filesystem MCP server
- **Git operations** -- Check status, view diffs, and manage branches
- **Web browsing** -- Automate browser interactions with Playwright
- **Document processing** -- Extract text from PDFs and Excel files
- **External integrations** -- Interact with GitHub, Linear, and other services

See [MCP Servers](/using-dryade/mcp) for the full list of available tools.

## Conversation History

All conversations are saved and accessible from the sidebar:

- **Browse history** -- Scroll through past conversations in the sidebar
- **Search** -- Find specific conversations by content
- **Continue** -- Pick up any conversation where you left off
- **Delete** -- Remove conversations you no longer need

## Code in Conversations

When the AI generates code, it appears in syntax-highlighted code blocks with:

- **Language detection** -- Automatic syntax highlighting for the detected language
- **Copy button** -- One-click copy for code snippets
- **Multi-file output** -- The AI can generate multiple files in a single response

## Tips

- **Be specific in your requests.** The more context you provide, the better the response. Include relevant details, constraints, and expected output format.
- **Use conversations for different topics.** Start a new conversation for each distinct topic to keep context clean and avoid confusion.
- **Enable MCP servers for richer interactions.** Tools make the AI significantly more capable -- it can read your files, check your Git history, and interact with external services.
- **Try different models.** Different models have different strengths. Use the model selector to find the best fit for your task.

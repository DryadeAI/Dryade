---
title: Plans & Features
sidebar_position: 2
---

# Plans & Features

Dryade offers three subscription tiers, each unlocking additional capabilities. The core platform is available to all users, with paid tiers providing expanded plugin access, higher limits, and dedicated support.

## Feature Comparison

| Feature | Community | Starter | Team | Enterprise |
|---------|-----------|---------|------|------------|
| **Core Platform** | | | | |
| Chat with AI models | Included | Included | Included | Included |
| Agent creation & execution | Included | Included | Included | Included |
| Workflow builder | Included | Included | Included | Included |
| Knowledge base management | Included | Included | Included | Included |
| MCP server integration | Included | Included | Included | Included |
| WebSocket & SSE streaming | Included | Included | Included | Included |
| Self-hosting | Included | Included | Included | Included |
| **Plugins** | | | | |
| Plugin Manager | -- | Included | Included | Included |
| Starter-tier plugins | -- | Included | Included | Included |
| Team-tier plugins | -- | -- | Included | Included |
| Enterprise-tier plugins | -- | -- | -- | Included |
| Custom plugin slots | -- | 5 | 15 | 25 |
| **Users & Limits** | | | | |
| Users per instance | 1 | 5 | 25 | Unlimited |
| **Support** | | | | |
| Community support (GitHub) | Included | Included | Included | Included |
| Email support | -- | Included | Included | Included |
| Priority support | -- | -- | Included | Included |
| Dedicated support channel | -- | -- | -- | Included |

## Community Edition

The community edition is free and includes the full core platform:

- Multi-provider AI chat (OpenAI, Anthropic, local models via vLLM, and more)
- Agent creation and autonomous task execution
- Visual workflow builder with approval gates
- Knowledge base with document ingestion
- MCP server integration for tool access
- WebSocket and SSE real-time streaming
- Self-hosted with full data sovereignty

Community users do not have access to the Plugin Manager or any tier-specific plugins.

## Starter

The Starter tier is designed for individuals and small teams getting started with plugin-based extensibility:

- Everything in Community, plus:
- Plugin Manager for loading and managing plugins
- Access to all Starter-tier plugins
- Up to 5 custom plugin slots for your own plugins
- Up to 5 users per instance
- Email support

## Team

The Team tier is built for growing teams that need collaboration features and advanced plugins:

- Everything in Starter, plus:
- Access to Team-tier plugins (analytics, collaboration, advanced integrations)
- Up to 15 custom plugin slots
- Up to 25 users per instance
- Priority support

## Enterprise

The Enterprise tier provides the full platform with advanced security, compliance, and unlimited scale:

- Everything in Team, plus:
- Access to Enterprise-tier plugins (compliance, audit logging, SSO, advanced security)
- Up to 25 custom plugin slots
- Unlimited users per instance
- Dedicated support channel

## Pricing

For current pricing, visit [dryade.ai/pricing](https://dryade.ai/pricing).

## Plugin Tier Details

Each plugin declares a minimum required tier in its manifest. The mapping is straightforward:

- **Starter plugins** work on Starter, Team, and Enterprise licenses
- **Team plugins** work on Team and Enterprise licenses
- **Enterprise plugins** work only on Enterprise licenses

Custom plugins you develop count against your custom plugin slot allocation. See the [Plugin Development](/plugin-development/structure) guide to learn how to build your own plugins.

## Upgrading

To upgrade your tier:

1. Visit [dryade.ai/pricing](https://dryade.ai/pricing) and select your plan
2. Complete the subscription process
3. Your license will be updated automatically
4. Restart your Dryade instance to load the new tier's plugins

For enterprise agreements or volume licensing, contact [contact@dryade.ai](mailto:contact@dryade.ai).

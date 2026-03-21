---
title: Changelog
sidebar_position: 3
---

# Changelog

A record of notable changes to Dryade across releases. This project follows [Semantic Versioning](https://semver.org/) and uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

:::note
This page will be auto-generated from the public repository commit history in CI. The entries below are manually maintained for the initial release.
:::

## Version Format

- **MAJOR** -- Breaking changes that require migration steps
- **MINOR** -- New features and capabilities (backwards compatible)
- **PATCH** -- Bug fixes and minor improvements (backwards compatible)

---

## v1.0.0

*Initial public release*

### Core Platform

- Multi-provider AI chat with streaming responses (OpenAI, Anthropic, local models via vLLM)
- Agent creation and autonomous task execution with ReAct loop orchestration
- Visual workflow builder with conditional logic, loops, and approval gates
- Knowledge base management with document ingestion and semantic search
- MCP (Model Context Protocol) server integration for tool access
- WebSocket and SSE real-time streaming for chat and agent execution
- JWT-based authentication with httpOnly cookies and optional TOTP MFA
- Provider fallback chains with health monitoring and automatic failover
- Hierarchical tool routing with semantic and regex matching

### Plugin System

- Plugin Manager with cryptographic plugin verification
- Three-tier plugin catalog: Starter, Team, and Enterprise
- Sandboxed iframe plugin UIs with DryadeBridge communication
- Plugin CLI (`dryade-pm push`) for local development workflow
- Schema-driven plugin settings with auto-generated forms

### Workbench (Frontend)

- Dark-first responsive UI built with React, TypeScript, and Tailwind CSS
- Workspace with chat, agents, workflows, knowledge, and plugin pages
- Real-time streaming display for thinking steps, tool calls, and responses
- Mobile-responsive layout with accessible navigation

### Deployment

- Docker Compose deployment for self-hosted environments
- SQLite (development) and PostgreSQL (production) database support
- Alembic database migrations
- Nginx reverse proxy configuration

### Documentation

- docs.dryade.ai documentation site (Docusaurus)
- Getting started guides, user documentation, and developer guides
- Plugin development guide from structure to publishing

---

*For the complete commit history, see the [GitHub repository](https://github.com/DryadeAI/Dryade/commits/main).*

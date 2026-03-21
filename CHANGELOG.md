# Changelog

All notable changes to Dryade will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-beta] - 2026-03-XX

Initial public release of Dryade.

### Added

**Core Platform**
- DryadeOrchestrator with ReAct loop supporting 3 modes: chat, planner, orchestrate
- Multi-agent orchestration with dynamic tool routing and capability-based agent selection
- MCP (Model Context Protocol) server integration for external tool connectivity
- Knowledge base with RAG pipeline (document ingestion, chunking, semantic search)
- Visual workflow builder for drag-and-drop agent pipelines with human-in-the-loop approval steps
- Conversation management with full history, context preservation, and streaming output
- Project-scoped workspaces for organizing agents, knowledge bases, and workflows

**LLM Support**
- Any OpenAI-compatible API provider (Ollama, vLLM, OpenAI, Anthropic via proxy, Mistral, Groq)
- Automatic model detection and capability assessment (tool calling, streaming, context window)
- Tool calling support with intelligent fallback for models without native tool_calls
- Streaming responses with real-time token output via WebSocket and SSE
- Provider auto-fallback and backpressure for production resilience

**Deployment**
- Docker Compose deployment with profiles (default, GPU, observability)
- Edge hardware support (NVIDIA Jetson, DGX Spark with Grace Blackwell)
- vLLM integration for local GPU inference with configurable memory utilization
- PostgreSQL and SQLite database support with automatic Alembic migrations
- Health check endpoints for all services
- TLS reverse proxy with self-signed (local) and Let's Encrypt (production) support
- Backup and restore scripts for all data stores

**Observability**
- Pre-built Grafana dashboards: System Overview, LLM Performance, MCP Health, Infrastructure
- Prometheus metrics collection with Alertmanager
- Log aggregation with Grafana Loki
- Distributed tracing with Jaeger

**Developer Experience**
- Full REST API with OpenAPI documentation
- WebSocket support for real-time communication
- Plugin system for extending platform functionality via marketplace
- Comprehensive documentation and getting started guide
- GitHub issue and PR templates
- Contributor License Agreement (CLA)

**Security**
- JWT authentication with session management
- TOTP multi-factor authentication with recovery codes
- MFA enforcement toggle with grace period for existing users
- Rate limiting with configurable RPM per endpoint category
- Non-root Docker containers
- Docker socket proxy for MCP gateway isolation
- Environment-based configuration (no hardcoded secrets)
- Vulnerability disclosure policy

### Infrastructure
- Community CI pipeline (lint, type check, unit tests, frontend build)
- Automated release workflow with changelog generation
- Docker Compose health checks on all services with resource limits
- Pinned container images for reproducible builds

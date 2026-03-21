# Test Coverage Gap Analysis

**Generated:** 2026-01-28
**Source:** pytest-cov analysis of core/ and plugins/ directories

---

## Executive Summary

**Overall Coverage:** 36% (7,648 covered / 21,173 total lines)
**Target Threshold:** 40% (configured in pyproject.toml)
**Gap to Close:** 4 percentage points

**Total Modules Analyzed:** 242
**Critical Gaps (< 30%):** 89 modules
**Moderate Gaps (30-50%):** 31 modules
**Adequate Coverage (> 50%):** 122 modules

---

## Critical Gaps (< 30% Coverage)

These modules represent the highest priority for test coverage improvement:

### Core Infrastructure (< 30%)

| Module | Coverage | Lines (Total/Uncovered) | Priority |
|--------|----------|------------------------|----------|
| `core/api/main.py` | 33% | 258 total, 174 uncovered | **CRITICAL** |
| `core/api/routes/chat.py` | 24% | 480 total, 367 uncovered | **CRITICAL** |
| `core/api/routes/workflows.py` | 28% | 462 total, 332 uncovered | **CRITICAL** |
| `core/api/routes/plugins.py` | 22% | 349 total, 272 uncovered | **CRITICAL** |
| `core/api/routes/plans.py` | 39% | 321 total, 195 uncovered | HIGH |
| `core/api/routes/files.py` | 36% | 193 total, 124 uncovered | HIGH |
| `core/api/routes/knowledge.py` | 34% | 179 total, 119 uncovered | HIGH |
| `core/api/routes/metrics_api.py` | 24% | 70 total, 53 uncovered | HIGH |
| `core/knowledge/sources.py` | 24% | 132 total, 100 uncovered | HIGH |
| `core/knowledge/embedder.py` | 24% | 37 total, 28 uncovered | MEDIUM |
| `core/agents/llm.py` | 24% | 25 total, 19 uncovered | MEDIUM |
| `core/crews/analysis_crew.py` | 28% | 43 total, 31 uncovered | MEDIUM |
| `core/crews/mbse_crew.py` | 24% | 45 total, 34 uncovered | MEDIUM |
| `core/flows/analysis_flow.py` | 36% | 88 total, 56 uncovered | MEDIUM |
| `core/flows/coverage_flow.py` | 31% | 84 total, 58 uncovered | MEDIUM |
| `core/extensions/decorator.py` | 19% | 57 total, 46 uncovered | MEDIUM |
| `core/auth/ownership.py` | 17% | 64 total, 53 uncovered | MEDIUM |
| `core/auth/sharing.py` | 29% | 35 total, 25 uncovered | MEDIUM |
| `core/api/middleware/tracing.py` | 25% | 32 total, 24 uncovered | LOW |

### Core Infrastructure (0% Coverage)

| Module | Lines | Priority |
|--------|-------|----------|
| `core/cli.py` | 136 | **CRITICAL** |
| `core/commands/handlers/__init__.py` | 92 | HIGH |
| `core/commands/handlers/agent.py` | 36 | HIGH |
| `core/commands/handlers/flow.py` | 42 | HIGH |
| `core/commands/handlers/rag.py` | 33 | HIGH |
| `core/capella_schema.py` | 40 | MEDIUM |
| `core/api/middleware/error_metrics.py` | 23 | MEDIUM |
| `core/api/middleware/validation.py` | 20 | MEDIUM |
| `core/api/websockets/costs_ws.py` | 62 | MEDIUM |
| `core/domains/__init__.py` | 75 | LOW |
| `core/domains/capella/__init__.py` | 9 | LOW |
| `core/domains/test/__init__.py` | 9 | LOW |

### Enterprise Plugins (0% Coverage)

| Plugin | Module | Lines | Priority |
|--------|--------|-------|----------|
| **audio** | All modules | 1,123 total | **CRITICAL** |
| | `audio/intelligence.py` | 188 | **CRITICAL** |
| | `audio/providers/vibevoice.py` | 125 | HIGH |
| | `audio/providers/piper.py` | 92 | HIGH |
| | `audio/providers/whisper.py` | 93 | HIGH |
| | `audio/agent.py` | 67 | MEDIUM |
| **trainer** | All modules | 1,362 total | **CRITICAL** |
| | `trainer/routes.py` | 356 | **CRITICAL** |
| | `trainer/runners.py` | 348 | **CRITICAL** |
| | `trainer/schemas.py` | 180 | HIGH |
| | `trainer/llm_router.py` | 97 | HIGH |
| **sandbox** | All modules | 393 total | HIGH |
| | `sandbox/executor.py` | 142 | **CRITICAL** |
| | `sandbox/cache.py` | 86 | HIGH |
| | `sandbox/registry.py` | 55 | MEDIUM |
| **self_healing** | All modules | 367 total | HIGH |
| | `self_healing/healer.py` | 191 | **CRITICAL** |
| | `self_healing/circuit_breaker.py` | 73 | HIGH |
| | `self_healing/decorator.py` | 46 | MEDIUM |
| **semantic_cache** | Most modules | 552 total (0%) | HIGH |
| | `semantic_cache/cache.py` | 140 | **CRITICAL** |
| | `semantic_cache/redis_store.py` | 117 | HIGH |
| | `semantic_cache/qdrant_store.py` | 97 | HIGH |
| | `semantic_cache/wrapper.py` | 84 | HIGH |
| **cost_tracker** | All modules | 127 total | HIGH |
| | `cost_tracker/tracker.py` | 70 | HIGH |
| **safety** | Validator module | 192 total | HIGH |
| | `safety/validator.py` | 192 | **CRITICAL** |
| **file_safety** | Scanner module | 248 total | HIGH |
| | `file_safety/scanner.py` | 248 | **CRITICAL** |
| **escalation** | Handler module | 82 total | MEDIUM |
| | `escalation/handler.py` | 82 | HIGH |
| **zitadel_auth** | Most modules | 233 total | MEDIUM |

### Community Plugins (Low Coverage)

| Plugin | Module | Coverage | Lines | Priority |
|--------|--------|----------|-------|----------|
| `message_hygiene` | `cleaner.py` | 10% | 87 total, 78 uncovered | HIGH |
| `clarify` | `protocol.py` | 24% | 147 total, 111 uncovered | HIGH |
| `checkpoint` | `store.py` | 28% | 86 total, 62 uncovered | MEDIUM |
| `mcp` | `bridge.py` | 34% | 104 total, 69 uncovered | MEDIUM |
| `debugger` | `flow_debugger.py` | 37% | 105 total, 66 uncovered | MEDIUM |
| `replay` | `replayer.py` | 44% | 96 total, 54 uncovered | MEDIUM |
| `flow_editor` | `editor.py` | 48% | 87 total, 45 uncovered | LOW |

---

## Adapter Coverage Analysis

Adapters are **critical path** code for framework integration:

| Adapter | Coverage | Lines (Total/Uncovered) | Status |
|---------|----------|------------------------|--------|
| `langchain_adapter.py` | **100%** | 41 total, 0 uncovered | ✅ EXCELLENT |
| `a2a_adapter.py` | **96%** | 48 total, 2 uncovered | ✅ EXCELLENT |
| `crewai_adapter.py` | **94%** | 64 total, 4 uncovered | ✅ EXCELLENT |
| `registry.py` | **100%** | 43 total, 0 uncovered | ✅ EXCELLENT |
| `adk_adapter.py` | **80%** | 88 total, 18 uncovered | ⚠️ GOOD |
| `protocol.py` | **92%** | 50 total, 4 uncovered | ✅ EXCELLENT |

**Verdict:** Adapter coverage is excellent (80-100%). Focus elsewhere.

---

## Extension Coverage Analysis

Extensions are **critical infrastructure** for core functionality:

| Extension | Coverage | Lines (Total/Uncovered) | Status |
|-----------|----------|------------------------|--------|
| `context.py` | **99%** | 86 total, 1 uncovered | ✅ EXCELLENT |
| `pipeline.py` | **89%** | 121 total, 13 uncovered | ✅ GOOD |
| `state.py` | **79%** | 160 total, 33 uncovered | ⚠️ GOOD |
| `events.py` | **77%** | 73 total, 17 uncovered | ⚠️ GOOD |
| `classifier.py` | **74%** | 123 total, 32 uncovered | ⚠️ FAIR |
| `latency_tracker.py` | **52%** | 54 total, 26 uncovered | ⚠️ NEEDS WORK |
| `request_queue.py` | **52%** | 79 total, 38 uncovered | ⚠️ NEEDS WORK |
| `decorator.py` | **19%** | 57 total, 46 uncovered | 🔴 CRITICAL |

**Verdict:** Extension coverage varies widely. Priority targets:
1. `decorator.py` (19%) - **CRITICAL GAP**
2. `request_queue.py` (52%) - Needs improvement
3. `latency_tracker.py` (52%) - Needs improvement

---

## Integration Test Coverage Gaps

Comparing integration test files against API route files:

### Routes with Integration Tests ✅

- ✅ `routes/agents.py` - `test_api_agents.py`
- ✅ `routes/auth.py` - `test_auth_routes.py`
- ✅ `routes/chat.py` - `test_api_chat.py`
- ✅ `routes/costs.py` - `test_api_costs.py`
- ✅ `routes/flows.py` - `test_api_flows.py` (indirectly via chat tests)
- ✅ `routes/health.py` - `test_api_health.py`
- ✅ `routes/knowledge.py` - `test_api_knowledge.py`
- ✅ `routes/metrics.py` - `test_api_metrics.py`
- ✅ `routes/plans.py` - `test_api_plans.py`
- ✅ `routes/plugins.py` - `test_api_plugins.py`
- ✅ `routes/workflows.py` - `test_api_workflows.py`
- ✅ `routes/websocket.py` - `test_websocket_reliability.py`

### Routes WITHOUT Integration Tests 🔴

- 🔴 `routes/cache.py` (77% coverage, but no dedicated integration test)
- 🔴 `routes/commands.py` (52% coverage, no integration test)
- 🔴 `routes/extensions.py` (74% coverage, no integration test)
- 🔴 `routes/files.py` (36% coverage, no integration test)
- 🔴 `routes/healing.py` (52% coverage, no integration test)
- 🔴 `routes/license.py` (74% coverage, no integration test)
- 🔴 `routes/metrics_api.py` (24% coverage, no integration test)
- 🔴 `routes/safety.py` (53% coverage, no integration test)
- 🔴 `routes/sandbox.py` (52% coverage, no integration test)
- 🔴 `routes/security_telemetry.py` (54% coverage, no integration test)
- 🔴 `routes/users.py` (56% coverage, no integration test)

**Note:** Many existing integration tests are currently failing due to database/auth setup issues. These need to be fixed before adding new tests.

---

## Top 10 Priority Modules for Coverage Improvement

Based on criticality + code volume + current coverage:

| Rank | Module | Coverage | Lines | Reason |
|------|--------|----------|-------|--------|
| **1** | `core/api/routes/chat.py` | 24% | 480 | Core chat functionality, highest uncovered volume |
| **2** | `core/api/routes/workflows.py` | 28% | 462 | Workflow lifecycle, critical business logic |
| **3** | `core/api/routes/plugins.py` | 22% | 349 | Plugin management, extensibility core |
| **4** | `plugins/trainer/routes.py` | 0% | 356 | Enterprise feature, high complexity |
| **5** | `plugins/trainer/runners.py` | 0% | 348 | Training execution, critical for trainer plugin |
| **6** | `core/api/main.py` | 33% | 258 | Application bootstrap, middleware setup |
| **7** | `plugins/file_safety/scanner.py` | 0% | 248 | Security-critical functionality |
| **8** | `plugins/audio/intelligence.py` | 0% | 188 | Audio processing, complex logic |
| **9** | `core/api/routes/plans.py` | 39% | 321 | Plan management, near threshold |
| **10** | `plugins/safety/validator.py` | 0% | 192 | Security validation, critical path |

---

## Recommendations

### Phase 1: Fix Existing Test Infrastructure 
- **Fix failing integration tests** (118 failures detected)
- Most failures are due to:
  - Database setup issues (ownership, sharing, workflows)
  - Authentication setup (401 Unauthorized responses)
  - Rate limiting configuration (429 Too Many Requests)
- Once fixed, rerun coverage to get accurate baseline

### Phase 2: Add Critical Route Integration Tests 
Focus on routes without any integration tests:
1. `routes/files.py` (36% coverage, file upload/download)
2. `routes/commands.py` (52% coverage, slash commands)
3. `routes/extensions.py` (74% coverage, extension management)
4. `routes/healing.py` (52% coverage, self-healing endpoints)
5. `routes/sandbox.py` (52% coverage, sandbox execution)

### Phase 3: Enterprise Plugin Coverage 
Prioritize security and business-critical plugins:
1. **file_safety** - Security scanning (248 lines, 0%)
2. **safety** - Content validation (192 lines, 0%)
3. **sandbox** - Isolated execution (393 lines, 0%)
4. **cost_tracker** - Usage tracking (127 lines, 0%)

### Phase 4: Extension Coverage Improvement
Focus on low-coverage critical infrastructure:
1. `decorator.py` (19%) - Extension decorator system
2. `latency_tracker.py` (52%) - Performance monitoring
3. `request_queue.py` (52%) - Request queuing

### Quick Wins
These modules are small and have 0% coverage - easy targets:
- `core/commands/handlers/agent.py` (36 lines)
- `core/commands/handlers/flow.py` (42 lines)
- `core/commands/handlers/rag.py` (33 lines)
- `core/api/middleware/error_metrics.py` (23 lines)
- `core/api/middleware/validation.py` (20 lines)

---

## Coverage Trend Tracking

| Date | Overall Coverage | Change | Note |
|------|------------------|--------|------|
| 2026-01-28 | 36% | Baseline | Initial measurement  |

**Target:** 40% (4 percentage point improvement)

---

## Notes

- **HTML Report Available:** `tests/htmlcov/index.html` for interactive exploration
- **Test Markers:** Some tests skipped due to `requires_llm` and `requires_mcp` markers
- **Coverage Config:** Source in pyproject.toml (omits test files, caches, venv)
- **Fail-Under Threshold:** 40% (currently failing at 36%)

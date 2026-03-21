// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Extended API Types for Dryade Platform

// ============== COST TYPES ==============
export interface ModelCost {
  model: string;
  total_cost: number;
  total_tokens: number;
  request_count: number;
  avg_cost_per_request: number;
  percentage: number;
}

export interface UserCost {
  user_id: string;
  display_name?: string;
  total_cost: number;
  total_tokens: number;
  request_count: number;
  avg_cost_per_request: number;
}

export interface AgentCost {
  agent_name: string;
  framework?: string;
  total_cost: number;
  total_tokens: number;
  request_count: number;
}

// ============== FILE SAFETY TYPES ==============
export interface ScanResult {
  safe: boolean;
  combined_threats: string[];
  scan_time: number;
  clamav_result: ScannerResult;
  yara_result: ScannerResult;
}

export interface ScannerResult {
  available: boolean;
  threats: string[];
  scan_time: number;
}

export interface QuarantineEntry {
  filename: string;
  original_path: string;
  quarantine_time: string;
  threats: string[];
  size_bytes: number;
}

export interface ScanStats {
  total_scans: number;
  clean_files: number;
  infected_files: number;
  quarantined_count: number;
  clamav_available: boolean;
  yara_rules_count: number;
  avg_scan_time_ms: number;
}

// ============== EXTENSIONS TYPES ==============
export interface ExtensionStatus {
  name: string;
  type: string;
  enabled: boolean;
  priority: number;
  health: "healthy" | "degraded" | "down";
}

export interface ExtensionMetrics {
  cache_hit_rate: number;
  cache_savings_usd: number;
  sandbox_overhead_ms: number;
  healing_success_rate: number;
  threats_blocked: number;
  validation_failures: number;
  total_requests: number;
}

export interface ExtensionConfig {
  extensions_enabled: boolean;
  input_validation_enabled: boolean;
  semantic_cache_enabled: boolean;
  self_healing_enabled: boolean;
  sandbox_enabled: boolean;
  file_safety_enabled: boolean;
  output_sanitization_enabled: boolean;
}

export interface CacheStats {
  total_queries: number;
  exact_hits: number;
  semantic_hits: number;
  fallback_hits?: number;
  misses: number;
  hit_rate: number;
  avg_lookup_time_ms?: number;
  memory_cache_size?: number;
  cache_size_bytes?: number;
  ttl_seconds?: number;
  config?: {
    enabled: boolean;
    similarity_threshold: number;
    exact_ttl_seconds: number;
    semantic_ttl_seconds: number;
  };
}

export interface SandboxConfig {
  isolation_level: "none" | "low" | "medium" | "high" | "strict";
  timeout_seconds: number;
  memory_limit_mb: number;
  allowed_tools: string[];
}

export interface SandboxStats {
  registry: {
    enabled: boolean;
    total_tools: number;
    default_level: string;
    levels_distribution: Record<string, number>;  // GAP-110 FIX: matches backend field name
  };
  cache: {
    size: number;
    hits: number;
    misses: number;
  };
}

export interface CircuitBreaker {
  name: string;
  state: "closed" | "open" | "half_open";
  failure_count: number;
  failure_threshold: number;
  timeout_seconds: number;
  last_failure?: string;
}

export interface SafetyStats {
  validation_failures: number;
  sanitization_events: number;
  most_common_violations: Array<{ type: string; count: number }>;
  sanitization_by_context: Record<string, number>;
}

export interface SafetyViolation {
  id: string;
  timestamp: string;
  type: "validation_failure" | "sanitization_event";
  details: string;
  severity: "low" | "medium" | "high";
}

// ============== METRICS TYPES ==============
export interface LatencyStats {
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  ttft_avg_ms?: number;
  total_requests: number;
  cache_hit_rate?: number;
}

// QueueStatus is defined in @/types/api - use that for backend compatibility

export interface ModeStats {
  mode: string;
  request_count: number;
  avg_latency_ms: number;
  success_rate: number;
  total_tokens: number;
}

export interface RecentRequest {
  id: string;
  timestamp: string;
  mode: string;
  latency_ms: number;
  tokens: number;
  status: "success" | "error";
  error_message?: string;
}

// ============== KNOWLEDGE TYPES ==============
export interface KnowledgeSource {
  id: string;
  name: string;
  source_type: "pdf" | "text" | "md" | "docx";
  chunk_count?: number;
  created_at: string;
  crews: string[]; // Maps to crew_ids from backend
  agents: string[]; // Maps to agent_ids from backend
  size_bytes?: number;
  status: "processing" | "ready" | "error";
  // Added for backend compatibility (GAP-069, GAP-070, GAP-071)
  description?: string;
  file_paths?: string[]; // Backend uses file_paths (list), not file_path
}

export interface SearchResult {
  content: string;
  score: number;
  metadata: {
    source_id?: string;
    source_name?: string;
    page?: number;
    chunk_index?: number;
  };
}

export interface UploadProgress {
  stage: "uploading" | "parsing" | "chunking" | "embedding" | "complete" | "error";
  progress: number;
  message?: string;
}

// ============== PLANS TYPES ==============
export type PlanStatus = "draft" | "approved" | "executing" | "completed" | "failed" | "cancelled";

/** Plan card data for inline chat display */
export interface PlanCardData {
  id?: number;                     // Plan ID from backend (undefined if unsaved)
  name: string;                    // Plan name
  description: string | null;      // Brief description
  confidence: number;              // 0.0-1.0 confidence score
  reasoning?: string;              // LLM reasoning for plan generation
  nodes: Array<{
    id: string;
    agent: string;
    task: string;
    depends_on?: string[];         // Node dependencies (matches backend)
    position?: { x: number; y: number };
  }>;
  edges: Array<{
    from: string;
    to: string;
  }>;
  status: PlanStatus;
  ai_generated: boolean;           // Flag for AI-generated workflows
  created_at: string;
  updated_at?: string;             // Last modification timestamp
  plan_json?: Record<string, unknown>;   // Wrapper for nodes/edges for UI contract
  estimated_cost?: number;         // Estimated cost if available
  approved_at?: string;            // ISO timestamp when plan was approved
  completed_at?: string;           // ISO timestamp when plan completed
  execution_count?: number;        // Number of times executed
  conversation_id?: string;        // Associated conversation ID
  user_id?: string;                // Creator user ID
}

export interface Plan {
  id: number; // int, not string
  name: string;
  description?: string; // GAP-055: add description
  status: PlanStatus;
  confidence?: number;
  estimated_cost?: number;
  reasoning?: string;
  conversation_id?: string; // GAP-053
  user_id?: string; // GAP-053
  nodes: PlanNode[];
  edges: PlanEdge[];
  created_at: string;
  updated_at: string;
  approved_at?: string;
  completed_at?: string;
  ai_generated?: boolean; // Phase 70-06: AI-generated flag
}

export type PlanNodeStatus = "pending" | "executing" | "completed" | "failed" | "skipped" | "degraded";

// GAP-054: Node types match backend
export interface PlanNode {
  id: string;
  type?: "start" | "task" | "router" | "end";  // Made optional -- backend doesn't always send this
  label?: string;                                // Display label (may be derived from agent)
  description?: string;
  status?: PlanNodeStatus;                       // Made optional -- draft plans have no status
  agent?: string;                                // Agent name (primary backend field)
  task?: string;                                 // Task description (primary backend field)
  tool?: string;
  arguments?: Record<string, unknown>;    // Tool arguments (JSON)
  duration_ms?: number;
  result?: string;
  error?: string;
  dependencies?: string[];                       // Legacy field name
  depends_on?: string[];                         // Backend field name (preferred)
}

export interface PlanEdge {
  id: string;
  source: string;
  target: string;
  condition?: string;
}

// Plan execution tracking (separate from plan lifecycle status)
export type PlanExecutionStatus = "executing" | "completed" | "failed" | "cancelled" | "timeout";

// Response from POST /api/plans/{id}/execute
export interface PlanExecutionStart {
  execution_id: string;
  plan_id: number;
  status: "executing";
  message?: string;
}

export interface PlanExecution {
  id: string; // execution_id
  plan_id: number;
  status: PlanExecutionStatus;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  total_cost?: number;
  user_feedback_rating?: number;
  user_feedback_comment?: string;
  created_at?: string;
  node_results: PlanNodeResult[];
}

export interface PlanNodeResult {
  node_id: string;
  status: PlanNodeStatus;
  output?: string;
  error?: string;
  duration_ms?: number;
  agent?: string;
  task?: string;
}

export interface PlanTemplate {
  name: string;
  description: string;
  category: string;
  parameters: Array<{
    name: string;
    type: string;
    required: boolean;
    default?: unknown;
  }>;
}

// ============== PLUGINS TYPES ==============
export type PluginCategory = "pipeline" | "backend" | "utility";
export type PluginStatus = "enabled" | "disabled" | "error" | "missing";

export interface Plugin {
  name: string;
  display_name: string;
  category: PluginCategory;
  status: PluginStatus;
  version: string;
  has_config: boolean;
  has_ui: boolean;
  required_tier?: string | null;
  health?: "healthy" | "degraded" | "unhealthy";
  description?: string;
  icon?: string;
  config?: Record<string, unknown>;
}

export interface MarketplacePlugin {
  name: string;
  display_name: string;
  description: string;
  version: string;
  author: string;
  tier: string; // starter | team | enterprise
  category: string;
  icon?: string;
  installed: boolean;
  available: boolean; // true if in user's current allowlist
  download_url?: string;
  rating?: number;
  install_count?: number;
}

export interface CatalogResponse {
  plugins: MarketplacePlugin[];
  total: number;
  tier_info: { name: string };
}

// ============== PROFILE TYPES ==============
export type UserRole = "admin" | "member";
export type PermissionLevel = "view" | "edit" | "owner";

export interface User {
  id: string;
  email: string;
  display_name?: string;
  avatar_color?: string;
  role: UserRole;
  is_external: boolean;
  first_seen: string;
  last_seen: string;
}

export interface ShareableResource {
  id: string;
  type: "conversation" | "workflow" | "agent" | "knowledge";
  name: string;
  shared_with: SharedUser[];
}

export interface SharedUser {
  user_id: string;
  email: string;
  display_name?: string;
  permission: PermissionLevel;
}

// ============== SETTINGS TYPES ==============
export interface AppSettings {
  appearance: AppearanceSettings;
  notifications: NotificationSettings;
  chat: ChatSettings;
  data: DataSettings;
}

export interface AppearanceSettings {
  theme: "light" | "dark" | "system";
  sidebar_collapsed: boolean;
  compact_mode: boolean;
  font_size: "small" | "medium" | "large";
}

export interface NotificationSettings {
  email_enabled: boolean;
  email_categories: {
    workflow_complete: boolean;
    plan_approval: boolean;
    system_alerts: boolean;
    weekly_digest: boolean;
  };
  sound_enabled: boolean;
  desktop_enabled: boolean;
}

export interface ChatSettings {
  default_mode: string;
  auto_scroll: boolean;
  show_timestamps: boolean;
  syntax_theme: "github" | "dracula" | "monokai" | "vs-code";
  expand_reasoning: boolean;
}

export interface DataSettings {
  auto_save: boolean;
  save_interval_seconds: number;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used?: string;
  expires_at?: string;
}

// ============== TRAINER TYPES (ENTERPRISE) ==============
export type JobType = "datagen" | "sft" | "dpo" | "eval";
export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface TrainingJob {
  id: string;
  name: string;
  job_type: JobType;
  status: JobStatus;
  progress: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  config: TrainingConfig;
  metrics?: TrainingMetrics;
  error_message?: string;
}

export interface TrainingConfig {
  base_model?: string;
  model_id?: string;
  dataset_id?: string;
  epochs?: number;
  learning_rate?: number;
  batch_size?: number;
  eval_model?: string;
  eval_dataset?: string;
}

export interface TrainingMetrics {
  loss?: number;
  accuracy?: number;
  eval_score?: number;
  samples_processed?: number;
  tokens_generated?: number;
}

export interface TrainingLog {
  timestamp: string;
  level: "info" | "warn" | "error";
  message: string;
}

// ============== MODELS TYPES (ENTERPRISE) ==============
export type ModelStatus = "available" | "loading" | "error" | "deprecated";

export interface Model {
  id: string;
  name: string;
  display_name: string;
  provider: string;
  status: ModelStatus;
  is_default: boolean;
  is_custom: boolean;
  base_model?: string; // Base model for fine-tuned models
  job_id?: string; // Training job ID (if trained via trainer)
  metrics?: ModelMetrics;
  config?: ModelConfig;
  created_at?: string;
}

export interface ModelMetrics {
  latency_avg_ms: number;
  tokens_per_second?: number;
  success_rate: number;
  total_requests?: number;
  cost_per_1k_tokens?: number;
  eval_score?: number; // Evaluation score from trainer
}

export interface ModelConfig {
  max_tokens: number;
  temperature: number;
  top_p: number;
  context_window: number;
}

export interface ModelComparison {
  models: Model[];
  metrics: string[];
}

// ============== MODEL CONFIGURATION TYPES ==============
export type ModelCapability = "llm" | "embedding" | "audio" | "vision";

export interface ModelConfigEntry {
  provider: string;
  model: string;
}

export interface ModelsConfig {
  llm: ModelConfigEntry;
  embedding: ModelConfigEntry;
  audio: ModelConfigEntry;
  vision: ModelConfigEntry;
  /** Custom endpoint URL for LLM provider (e.g., Ollama, vLLM) */
  llm_endpoint?: string;
  /** Custom endpoint URL for ASR provider (e.g., vLLM) */
  asr_endpoint?: string;
  /** Custom endpoint URL for Embedding provider */
  embedding_endpoint?: string;
  /** Per-capability inference parameters */
  llm_inference_params?: InferenceParams;
  vision_inference_params?: InferenceParams;
  audio_inference_params?: InferenceParams;
  embedding_inference_params?: InferenceParams;
  /** vLLM server parameters */
  vllm_server_params?: InferenceParams;
}

/** Inference parameter specification from backend */
export interface ParamSpec {
  name: string;
  type: "float" | "int" | "string_list" | "enum";
  min: number | null;
  max: number | null;
  default: number | string | string[];
  step: number;
  label: string;
  description: string;
}

/** Response from GET /api/models/provider-params */
export interface ProviderParamsResponse {
  provider_params: Record<string, string[]>;
  param_specs: Record<string, ParamSpec>;
  presets: Record<string, Record<string, number>>;
  capability_support: Record<string, string[]>;
  vllm_server_params: Record<string, ParamSpec>;
}

/** Inference params stored per capability */
export type InferenceParams = Record<string, number | string | string[]>;

export interface ProviderInfo {
  name: string;
  display_name: string;
  models: string[];
  requires_api_key: boolean;
  capabilities: ModelCapability[];
}

export interface ApiKeyInfo {
  provider: string;
  key_prefix: string;
  is_global: boolean;
  model_override: string | null;
  created_at: string;
}

export interface TestConnectionResult {
  provider: string;
  valid: boolean;
  message: string;
  models_available?: string[];
}

// ============== PROVIDER REGISTRY TYPES ==============
export interface ProviderCapabilities {
  llm: boolean;
  embedding: boolean;
  vision: boolean;
  audio_asr: boolean;
  audio_tts: boolean;
}

export interface ModelsByCapability {
  llm: string[];
  embedding: string[];
  vision: string[];
  audio_asr: string[];
  audio_tts: string[];
}

export interface ProviderWithCapabilities {
  id: string;
  name: string; // alias for id for compatibility
  display_name: string;
  auth_type: string;
  requires_api_key: boolean;
  supports_custom_endpoint: boolean;
  capabilities: ProviderCapabilities;
  has_key: boolean;
  base_url: string | null;
  models: string[]; // all models (backward compatibility)
  models_by_capability?: ModelsByCapability; // models grouped by capability
  is_custom?: boolean; // true for user-defined providers
}

// ============== CUSTOM PROVIDER TYPES ==============
export interface CustomProviderCreate {
  display_name: string;
  base_url: string;
  requires_api_key: boolean;
  capabilities: string[];
}

export interface CustomProviderResponse {
  id: number;
  slug: string;
  display_name: string;
  base_url: string;
  requires_api_key: boolean;
  capabilities: string[];
  created_at: string;
  updated_at: string;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  models?: string[];
  error_code?: string;
}

export interface ModelDiscoveryResult {
  provider: string;
  endpoint?: string;
  models: string[];
  error?: string;
}

// ============== WORKFLOW SCENARIO TYPES ==============
export interface ScenarioTriggerInfo {
  chat_command?: string;
  api_endpoint?: string;
  ui_button?: {
    label: string;
    location: string;
  };
}

export interface ScenarioInfo {
  name: string;
  display_name: string;
  description: string;
  domain: string;
  version: string;
  triggers: ScenarioTriggerInfo;
}

export interface ScenarioInputSchema {
  name: string;
  type: string;
  required: boolean;
  description: string;
  default?: unknown;
}

export interface ScenarioOutputSchema {
  name: string;
  type: string;
}

export interface ScenarioDetail extends ScenarioInfo {
  inputs: ScenarioInputSchema[];
  outputs: ScenarioOutputSchema[];
  required_agents: string[];
  observability: Record<string, boolean>;
}

export interface ScenarioWorkflowNodeData {
  agent?: string;
  task?: string;
  context?: Record<string, unknown>;
  condition?: string;
  branches?: Array<{ condition: string; target: string }>;
}

export interface ScenarioWorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data?: ScenarioWorkflowNodeData;
  metadata?: Record<string, string>;
}

export interface ScenarioWorkflowEdge {
  id: string;
  source: string;
  target: string;
  data?: Record<string, string>;
}

export interface ScenarioWorkflowGraph {
  version: string;
  metadata: Record<string, string>;
  nodes: ScenarioWorkflowNode[];
  edges: ScenarioWorkflowEdge[];
}

export interface ScenarioCheckpoint {
  node_id: string;
  timestamp: string;
  state_keys: string[];
}

// ============== CODE EXECUTION TYPES ==============
export interface CodeExecuteRequest {
  code: string;
  language: "python" | "bash" | "sh";
  timeout_seconds?: number;
}

export interface CodeExecuteResponse {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number;
  execution_time_ms: number;
}

export type CodeExecutionStatus = "idle" | "running" | "complete" | "error";

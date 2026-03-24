import axios from 'axios'

export type EventStatus = 'ACTIVE' | 'DRAFT' | 'DEPRECATED'
export type GovernanceVerdict = 'APPROVE' | 'REJECT' | 'NEEDS_REVISION'
export type PipelineStatus =
  | 'PENDING'
  | 'PROVISIONING'
  | 'RUNNING'
  | 'FAILED'
  | 'ROLLING_BACK'
  | 'STOPPED'

export interface TrackingEvent {
  id: number
  code: string
  name: string
  description: string
  domain: string
  status: EventStatus
  properties: Record<string, unknown>
  version: string
  owner?: string | null
  tags: string[]
  governance_status: 'NOT_CHECKED' | 'APPROVED' | 'NEEDS_REVISION' | 'REJECTED' | string
  project_id: number
  created_at: string
  updated_at: string
}

export interface GovernanceResult {
  check_id: number
  event_id: number | null
  verdict: GovernanceVerdict
  score: number
  reasoning: string
  recommended_code?: string
  risks: string[]
  suggestions: GovernanceSuggestion[]
  model_name: string
  similar_events: GovernanceSimilarEvent[]
}

export interface GovernanceSuggestion {
  title: string
  rationale: string
  patch: Record<string, unknown>
}

export interface GovernanceSimilarEvent {
  id: string | number
  score: number
  payload: Record<string, unknown>
  source: string
}

export interface EventGovernanceRecord {
  id: number
  verdict: GovernanceVerdict
  score: number
  reasoning: string
  recommended_code?: string | null
  model_name?: string
  risks?: string[]
  suggestions?: GovernanceSuggestion[]
  actor_id: string
  created_at: string
}

export interface EventRelatedPipeline {
  id: number
  event_code: string
  status: PipelineStatus
  topic_name: string
  flink_job_name: string
  updated_at: string
}

export interface EventVersionHistoryItem {
  id: number
  from_version: string
  to_version: string
  diff: Record<string, unknown>
  actor_id: string
  created_at: string
}

export interface EventDataQualityRule {
  id: number
  name: string
  asset_id?: number | null
  rule_type: string
  target_field?: string | null
  operator?: string | null
  threshold: Record<string, unknown>
  alert_channels?: string[]
  severity: string
  status: string
  description?: string | null
  version: string
  created_at: string
  updated_at: string
}

export interface EventDetailResponse {
  event: TrackingEvent
  governance_records: EventGovernanceRecord[]
  related_pipelines: EventRelatedPipeline[]
  data_quality_rules: EventDataQualityRule[]
  version_history: EventVersionHistoryItem[]
}

export interface GovernanceApplySuggestionsResponse {
  check_id: number
  event: TrackingEvent
  applied_indexes: number[]
  diff: Record<string, unknown>
}

export type AuditLogStatus = 'SUCCESS' | 'FAILURE'

export interface AuditLogContext {
  tenant_id?: number | null
  project_id?: number | null
  ip_address?: string | null
  actor_raw?: string | null
}

export interface AuditLogListItem {
  id: number
  user: string
  action: string
  entity_type: string
  entity_id: string
  target: string
  timestamp: string
  status: AuditLogStatus
  context: AuditLogContext
  trace_id?: string | null
  details_summary: string
  has_diff: boolean
  changed_fields: string[]
}

export interface AuditLogListResponse {
  items: AuditLogListItem[]
  total: number
  limit: number
  offset: number
  facets: {
    actions: string[]
    entity_types: string[]
    users: string[]
    trace_ids?: string[]
  }
}

export interface AuditLogDetailResponse {
  id: number
  user: string
  action: string
  entity_type: string
  entity_id: string
  target: string
  timestamp: string
  status: AuditLogStatus
  context: AuditLogContext
  trace_id?: string | null
  details_summary: string
  operation: {
    key_fields: Record<string, unknown>
    details: Record<string, unknown>
  }
  diff: Record<string, unknown>
  navigation: {
    module_route?: string | null
    entity_type: string
    entity_id: string
  }
}

export interface AuditLogExportResponse {
  format: 'csv' | 'json' | string
  filename: string
  mime_type: string
  row_count: number
  content: string
}

export interface Pipeline {
  id: number
  project_id: number
  event_code: string
  topic_name: string
  flink_job_name: string
  status: PipelineStatus
  config: Record<string, unknown>
  error_message?: string | null
  retry_count: number
  last_sync_at?: string | null
  created_at: string
  updated_at: string
}

export interface PipelineHistoryItem {
  id: number
  from_status: string | null
  to_status: string
  reason: string | null
  source: string
  synced_at: string
}

export interface DataAsset {
  id: number
  project_id: number
  name: string
  asset_type: 'TABLE' | 'TOPIC' | 'VIEW' | 'METRIC' | string
  source_system: string
  database_name?: string | null
  object_name: string
  domain: string
  owner?: string | null
  status: 'ACTIVE' | 'DRAFT' | 'DEPRECATED' | string
  tags: string[]
  description?: string | null
  schema_definition: Record<string, unknown>
  version: string
  created_at: string
  updated_at: string
}

export interface DataAssetDetailQualityRule {
  id: number
  name: string
  rule_type: string
  target_field?: string | null
  operator?: string | null
  threshold: Record<string, unknown>
  severity: string
  status: string
  version: string
  updated_at: string
}

export interface DataAssetDetailAlert {
  id: number
  source_type: string
  source_id: string
  severity: string
  title: string
  description: string
  status: string
  created_at: string
}

export interface DataAssetRelationEvent {
  id: number
  code: string
  name: string
  governance_status: string
}

export interface DataAssetRelationPipeline {
  id: number
  event_code: string
  topic_name: string
  flink_job_name: string
  status: PipelineStatus
  updated_at: string
}

export interface DataAssetVersionHistoryItem {
  id: number
  from_version: string
  to_version: string
  diff: Record<string, unknown>
  actor_id: string
  created_at: string
}

export interface DataAssetDetailResponse {
  asset: DataAsset
  lineage: {
    upstream: DataAsset[]
    downstream: DataAsset[]
  }
  quality: {
    rules: DataAssetDetailQualityRule[]
    alerts: DataAssetDetailAlert[]
  }
  relations: {
    events: DataAssetRelationEvent[]
    pipelines: DataAssetRelationPipeline[]
  }
  version_history: DataAssetVersionHistoryItem[]
}

export interface DataQualityRule {
  id: number
  project_id: number
  asset_id?: number | null
  event_id: number
  name: string
  rule_type: string
  target_field?: string | null
  operator?: string | null
  threshold: Record<string, unknown>
  alert_channels: string[]
  severity: string
  status: string
  description?: string | null
  version: string
  asset?: {
    id: number
    name: string
    asset_type: string
    object_name: string
    domain: string
  } | null
  event?: {
    id: number
    code: string
    name: string
    governance_status: string
  } | null
  last_run?: {
    result: 'PASS' | 'FAIL'
    checked_count: number
    failed_count: number
    pass_rate: number
    executed_at: string
    triggered_by: string
  } | null
  created_at: string
  updated_at: string
}

export interface DataQualityRuleOptionEvent {
  id: number
  code: string
  name: string
  domain: string
  governance_status: string
}

export interface DataQualityRuleOptionAsset {
  id: number
  name: string
  asset_type: string
  object_name: string
  domain: string
  status: string
}

export interface DataQualityRuleOptionsResponse {
  events: DataQualityRuleOptionEvent[]
  assets: DataQualityRuleOptionAsset[]
}

export interface DataQualityRuleExecutionResult {
  id: number
  result: 'PASS' | 'FAIL'
  checked_count: number
  failed_count: number
  pass_rate: number
  details: Record<string, unknown>
  error_message?: string | null
  triggered_by: string
  executed_at: string
}

export interface DataQualityRuleAlertItem {
  id: number
  severity: string
  title: string
  description: string
  status: string
  created_at: string
  resolved_at?: string | null
}

export interface DataQualityRuleVersionHistoryItem {
  id: number
  from_version: string
  to_version: string
  diff: Record<string, unknown>
  actor_id: string
  created_at: string
}

export interface DataQualityRuleDetailResponse {
  rule: DataQualityRule
  recent_results: DataQualityRuleExecutionResult[]
  trend: Array<{ executed_at: string; pass_rate: number; result: 'PASS' | 'FAIL' }>
  alerts: DataQualityRuleAlertItem[]
  version_history: DataQualityRuleVersionHistoryItem[]
}

export interface DataQualityRuleRunResponse {
  execution_id: number
  rule_id: number
  result: 'PASS' | 'FAIL'
  checked_count: number
  failed_count: number
  pass_rate: number
  max_failure_rate: number
  triggered_by: string
  executed_at: string
}

export type SchedulerDagStatus = 'ACTIVE' | 'PAUSED' | 'DRAFT' | 'DEPRECATED' | string
export type SchedulerTriggerMode = 'MANUAL' | 'CRON' | 'DEPENDENCY' | string
export type SchedulerRunStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'SKIPPED' | string
export type SchedulerNodeStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'SKIPPED' | string

export interface SchedulerOptionAsset {
  id: number
  name: string
  asset_type: string
  object_name: string
  domain: string
  status: string
}

export interface SchedulerOptionsResponse {
  task_types: string[]
  assets: SchedulerOptionAsset[]
}

export interface SchedulerRun {
  id: number
  project_id: number
  dag_id: number
  status: SchedulerRunStatus
  trigger_source: string
  triggered_by: string
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
  error_message?: string | null
  summary: Record<string, number>
  run_context: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SchedulerDagSummary {
  id: number
  project_id: number
  name: string
  description?: string | null
  status: SchedulerDagStatus
  trigger_mode: SchedulerTriggerMode
  cron_expr?: string | null
  timezone: string
  dependency_mode: string
  retry_policy: Record<string, unknown>
  schedule_config: Record<string, unknown>
  version: string
  node_count: number
  edge_count: number
  last_scheduled_at?: string | null
  next_scheduled_at?: string | null
  latest_run?: SchedulerRun | null
  created_at: string
  updated_at: string
}

export interface SchedulerDagNode {
  id: number
  dag_id: number
  project_id: number
  node_key: string
  name: string
  task_type: string
  input_assets: string[]
  output_assets: string[]
  logic_description?: string | null
  config: Record<string, unknown>
  position: Record<string, unknown>
  is_active: boolean
  latest_status?: SchedulerNodeStatus | null
  created_at: string
  updated_at: string
}

export interface SchedulerDagEdge {
  id: number
  dag_id: number
  from_node_id: number
  to_node_id: number
  from_node_key?: string | null
  to_node_key?: string | null
  condition: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SchedulerDagDetailResponse {
  dag: SchedulerDagSummary
  topology: {
    nodes: SchedulerDagNode[]
    edges: SchedulerDagEdge[]
  }
  schedule: {
    trigger_mode: SchedulerTriggerMode
    cron_expr?: string | null
    timezone: string
    dependency_mode: string
    retry_policy: Record<string, unknown>
    schedule_config: Record<string, unknown>
    last_scheduled_at?: string | null
    next_scheduled_at?: string | null
  }
  recent_runs: SchedulerRun[]
}

export interface SchedulerNodeRun {
  id: number
  run_id: number
  dag_id: number
  node_id: number
  node_key?: string | null
  node_name?: string | null
  status: SchedulerNodeStatus
  attempt: number
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  log_summary?: string | null
  error_message?: string | null
  upstream_snapshot: Record<string, string>
  metrics: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SchedulerRunDetailResponse {
  dag: SchedulerDagSummary
  run: SchedulerRun
  latest_node_status: Record<string, SchedulerNodeStatus>
  node_runs: SchedulerNodeRun[]
}

export interface SchedulerDagRunResponse {
  run: SchedulerRun
  node_runs: SchedulerNodeRun[]
}

export interface SchedulerEngineTickResponse {
  executed_count: number
  executed_runs: Array<{
    dag_id: number
    run_id: number
    status: SchedulerRunStatus
    next_scheduled_at?: string | null
  }>
}

export interface PipelineProvisionEventOption {
  id: number
  code: string
  name: string
  domain: string
  status: string
  governance_status: string
}

export interface PipelineProvisionOptionsResponse {
  approved_events: PipelineProvisionEventOption[]
}

export interface AuthUser {
  id: number
  email: string
  name: string
}

export interface AuthProject {
  id: number
  name: string
  role: string
}

export interface AuthTenant {
  id: number
  name: string
  slug: string
  status: string
  role: string
  projects: AuthProject[]
}

export interface AuthContextSelection {
  tenant_id: number
  project_id: number
}

export interface AuthResolvedContext {
  tenant_id: number
  tenant_name: string
  tenant_slug: string
  tenant_role: string
  project_id: number
  project_name: string
  project_role: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at: string
  user: AuthUser
  tenants: AuthTenant[]
  default_context: AuthContextSelection | null
}

export interface RegisterPayload {
  email: string
  password: string
  name: string
  tenant_slug?: string
  project_id?: number
}

export interface MeResponse {
  user: AuthUser
  tenants: AuthTenant[]
  default_context: AuthContextSelection | null
}

export interface SwitchContextResponse {
  user: AuthUser
  context: AuthResolvedContext
  tenants: AuthTenant[]
  default_context: AuthContextSelection | null
}

export type PlannerJsonScalar = string | number | boolean | null
export type PlannerJsonValue = PlannerJsonScalar | PlannerJsonValue[] | { [key: string]: PlannerJsonValue }

export type AnalysisQuestionWeight = 'LIGHT' | 'HEAVY'
export type AnalysisPlanStatus = 'GENERATED' | 'REVIEW_REQUIRED' | 'REVIEW_CONFIRMED' | 'REJECTED'
export type ConflictType =
  | 'FIELD_FACT_MISMATCH'
  | 'HIGH_COST_REVIEW'
  | 'BUSINESS_DEFINITION_MISMATCH'
  | 'PERMISSION_BLOCKER'
export type AnalysisResultKind = 'TABLE' | 'DATASET'
export type AnalysisFreshnessMode = 'ON_DEMAND' | 'BATCH'
export type AnalysisRecommendedEngine = 'duckdb' | 'SPARK_SQL'

export interface MetricCandidate {
  metric_key: string
  label: string
  domain?: string | null
  is_core_metric: boolean
}

export interface ConflictItem {
  conflict_type: ConflictType
  summary: string
  metric_key?: string | null
  is_core_metric: boolean
  requires_cross_source_access: boolean
}

export interface ReviewRequirement {
  code: string
  summary: string
}

export interface OfficialEvidenceItem {
  title: string
  summary: string
  content: string
  doc_type: string
  module: string
  tags: string[]
  meta_payload: Record<string, PlannerJsonValue>
}

export interface HistoricalEvidenceItem {
  name: string
  description: string
  kind: string
  scenario: string
  status: string
  tags: string[]
  query_payload: Record<string, PlannerJsonValue>
  cached_result_payload: Record<string, PlannerJsonValue>
}

export interface FieldFactEvidenceItem {
  name: string
  asset_type: string
  source_system: string
  database_name: string
  object_name: string
  domain: string
  description: string
  schema_definition: Record<string, PlannerJsonValue>
  tags: string[]
}

export interface AnalysisEvidenceBundle {
  official: OfficialEvidenceItem[]
  historical: HistoricalEvidenceItem[]
  field_facts: FieldFactEvidenceItem[]
}

export interface ResultServicePlan {
  result_kind: AnalysisResultKind
  freshness_mode: AnalysisFreshnessMode
  publishable: boolean
  recommended_engine: AnalysisRecommendedEngine
  reuse_key: string
}

export interface AnalysisPlanSummary {
  id: number
  project_id: number
  tenant_id: number
  question: string
  status: AnalysisPlanStatus
  question_weight: AnalysisQuestionWeight
  metric_candidates: MetricCandidate[]
  conflicts: ConflictItem[]
  review_requirements: ReviewRequirement[]
  evidence_bundle: AnalysisEvidenceBundle
  result_service_plan: ResultServicePlan
  collaboration_workflow_id: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AnalysisPlanDetail extends AnalysisPlanSummary {}

export interface GenerateAnalysisPlanPayload {
  question: string
  question_weight: AnalysisQuestionWeight
  metric_candidates: MetricCandidate[]
  conflicts: ConflictItem[]
  review_requirements: ReviewRequirement[]
  evidence_bundle: AnalysisEvidenceBundle
  result_service_plan: ResultServicePlan
}

export interface AnalysisPlanListResponse {
  items: AnalysisPlanSummary[]
  total: number
}

export interface ReviewAnalysisPlanPayload {
  action: 'CONFIRM' | 'REJECT'
  note?: string | null
}

interface ApiEnvelope<T> {
  code: string
  message: string
  data: T
}

export interface OverviewKpis {
  total_events: number
  governance_checks_30d: number
  approval_rate: number | null
  active_pipelines: number
  failed_pipelines: number
}

export interface OverviewActivityItem {
  id: string
  user: string
  action: string
  target: string
  timestamp: string
  status: 'SUCCESS' | 'FAILURE'
}

export interface OverviewRiskPipeline {
  id: number
  event_code: string
  topic_name: string
  flink_job_name: string
  status: PipelineStatus
  last_sync_at?: string | null
  error_message?: string | null
}

export interface OverviewRiskEvent {
  id: number
  event_name: string
  verdict: GovernanceVerdict
  score: number
  reasoning: string
  actor: string
  timestamp: string
}

export interface OverviewUnhandledAlert {
  id: number
  source_type: string
  source_id: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string
  title: string
  description: string
  status: string
  created_at: string
}

export interface OverviewTodoItem {
  id: string
  type: 'PIPELINE' | 'GOVERNANCE' | 'ALERT' | string
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string
  status: 'OPEN' | 'DONE' | string
  title: string
  description: string
  target: {
    type: string
    id: string
    label: string
  }
  created_at: string
}

export interface OverviewResponse {
  kpis: OverviewKpis
  recent_activity: OverviewActivityItem[]
  risks: {
    high_risk_events: OverviewRiskEvent[]
    pipelines: OverviewRiskPipeline[]
    unhandled_alerts: OverviewUnhandledAlert[]
  }
  todos: OverviewTodoItem[]
}

export interface P0SourceStat {
  event_name: string
  event_count: number
}

export interface P0SourceProfile {
  id?: number
  channel_id: number
  event_name: string
  total_events: number
  accepted_events: number
  last_seen_at?: string | null
  sdk_version?: string | null
  heat: 'HOT' | 'WARM' | 'COLD' | string
  updated_at?: string | null
}

export interface P0UnknownSignal {
  id: number
  event_id: number
  target_field: string
  source_paths: string[]
  field_frequency: number
  updated_at?: string | null
}

export interface P0ProposalItem {
  id: number
  event_id: number
  target_field: string
  source_paths: string[]
  status: string
  confidence_score: number
  field_frequency: number
  proposed_by: string
  ai_reasoning?: string | null
  recommended_action: string
  updated_at?: string | null
}

export interface P0InferenceCandidate {
  id: number
  mapping_id?: number | null
  candidate_type: 'SEMANTIC_MAPPING' | 'UNMAPPED_SIGNAL' | string
  event_id: number
  target_field: string
  source_paths: string[]
  status: string
  confidence_score: number
  field_frequency: number
  proposed_by: string
  reasoning?: string | null
  recommended_action: string
  last_observed_at?: string | null
  updated_at?: string | null
}

export interface P0DecisionItem {
  id: number
  event_id: number
  target_field: string
  status: string
  actor?: string | null
  note?: string | null
  updated_at?: string | null
}

export interface P0ContractItem {
  mapping_id: number
  event_id: number
  event_code: string
  contract_name: string
  target_field: string
  cast_type: string
  approved_by?: string | null
  updated_at?: string | null
}

export interface P0GovernanceQueueItem {
  id: number
  event_id: number
  target_field: string
  status: string
  confidence_score: number
  field_frequency: number
  recommended_action: string
  updated_at?: string | null
}

export interface P0ContractArtifact {
  id?: number
  event_id: number
  event_code: string
  contract_name: string
  approved_rule_count: number
  published_at?: string | null
  serving_status: string
  updated_at?: string | null
}

export interface P0GovernanceRecord {
  id: number
  mapping_id?: number | null
  event_id: number
  target_field: string
  decision_status: string
  queue_status: 'OPEN' | 'CLOSED' | string
  confidence_score: number
  field_frequency: number
  recommended_action: string
  actor?: string | null
  note?: string | null
  decided_at?: string | null
  updated_at?: string | null
}

export interface P0ObjectDetailState {
  object_type: 'SOURCE_PROFILE' | 'INFERENCE_CANDIDATE' | 'GOVERNANCE_RECORD' | 'CONTRACT_ARTIFACT'
  object_id: number
}

export interface P0EntityListResponse<T> {
  items: T[]
  total: number
  limit?: number
  offset?: number
}

export interface P0SourceProfileQuery {
  limit?: number
  offset?: number
  heat?: string
  q?: string
}

export interface P0InferenceCandidateQuery {
  limit?: number
  offset?: number
  candidate_type?: string
  status?: string
  q?: string
}

export interface P0GovernanceRecordQuery {
  limit?: number
  offset?: number
  queue_status?: string
  decision_status?: string
  q?: string
}

export interface P0ContractArtifactQuery {
  limit?: number
  offset?: number
  serving_status?: string
  q?: string
}

export type SourceOnboardingType = 'POSTGRESQL' | 'MYSQL' | 'SQLITE'

export interface SourceOnboardingConfig {
  host?: string
  port?: number
  database?: string
  schema?: string
  username?: string
  password?: string
  file_path?: string
  namespace?: string
  memory_scope?: 'PRIVATE' | 'TENANT' | string
}

export interface SourceOnboardingDiscoveryObject {
  source_type: string
  schema: string
  table_name: string
  row_count_estimate: number
  estimated_bytes?: number
  heat_level?: string
  column_count: number
  columns: Array<{
    name: string
    data_type: string
    nullable: boolean
  }>
  key_candidates: string[]
  time_candidates: string[]
  inference_candidates: Array<{
    candidate_type: string
    target_field: string
    source_paths: string[]
    confidence_score: number
    field_frequency: number
    reasoning: string
    recommended_action: string
  }>
}

export interface SourceOnboardingSource {
  id: number
  source_name: string
  source_type: SourceOnboardingType | string
  status: string
  heat_level?: string
  total_objects?: number
  total_rows?: number
  estimated_bytes?: number
  config: SourceOnboardingConfig
  last_test_status?: string | null
  last_test_message?: string | null
  last_tested_at?: string | null
  last_scan_status?: string | null
  last_scan_message?: string | null
  last_scanned_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  discovery?: {
    source_type: string
    schema: string
    objects: SourceOnboardingDiscoveryObject[]
  }
}

export interface SourceOnboardingListResponse {
  items: SourceOnboardingSource[]
  total: number
  page: number
  page_size: number
  total_pages: number
  supported_source_types: string[]
}

export interface SourceOnboardingConnectionResult {
  status: string
  message: string
  source: SourceOnboardingSource
}

export interface SourceOnboardingScanResult {
  source: SourceOnboardingSource
  discovery: {
    source_type: string
    schema: string
    objects: SourceOnboardingDiscoveryObject[]
  }
}

export interface SourceOnboardingDeleteResult {
  id: number
  source_name: string
  deleted: boolean
}

export interface ConnectorConfigField {
  key: string
  label: string
  type: string
  required?: boolean
  placeholder?: string | null
  default?: unknown
}

export interface ConnectorDefinition {
  id: number
  connector_key: string
  category: string
  display_name: string
  runtime_family: string
  status: string
  description?: string | null
  capabilities: string[]
  auth_modes: string[]
  config_schema: ConnectorConfigField[]
}

export interface SourceIntakePagedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
  facets?: Record<string, unknown>
}

export interface SourceInstance {
  id: number
  project_id: number
  connector_definition_id: number
  connector_key: string
  connector_name: string
  category: string
  runtime_family: string
  connector_status: string
  capabilities: string[]
  auth_modes: string[]
  instance_name: string
  status: string
  memory_scope_default: string
  config: Record<string, unknown>
  heat_level: string
  asset_count: number
  row_count_estimate: number
  estimated_bytes: number
  last_test_status?: string | null
  last_test_message?: string | null
  last_tested_at?: string | null
  last_discover_status?: string | null
  last_discover_message?: string | null
  last_discovered_at?: string | null
  last_watch_status?: string | null
  last_watch_message?: string | null
  last_watched_at?: string | null
  watch_enabled: boolean
  watch_interval_seconds: number
  watch_next_run_at?: string | null
  watch_last_started_at?: string | null
  watch_last_finished_at?: string | null
  watch_failure_count: number
  last_brief_title?: string | null
  last_brief_summary?: string | null
  created_at?: string | null
  updated_at?: string | null
  recent_briefs?: SourceBrief[]
  latest_assets?: SourceAsset[] | SourceIntakePagedResponse<SourceAsset>
}

export interface SourceAsset {
  id: number
  instance_id: number
  asset_key: string
  asset_type: string
  qualified_name: string
  display_name: string
  status: string
  heat_level: string
  inferred_domain?: string | null
  row_count_estimate: number
  estimated_bytes: number
  column_count: number
  field_count?: number
  semantic_candidate_count?: number
  update_mode: string
  last_seen_at?: string | null
  schema_payload: Record<string, unknown>
  metrics_payload: Record<string, unknown>
  updated_at?: string | null
}

export interface SourceFieldProfile {
  id: number
  field_id: number
  asset_id: number
  snapshot_id?: number | null
  null_ratio: number
  distinct_ratio: number
  sample_values: string[]
  min_value?: string | null
  max_value?: string | null
  observed_row_count: number
  profile_payload: Record<string, unknown>
  profiled_at?: string | null
}

export interface SemanticCandidate {
  id: number
  instance_id?: number | null
  asset_id?: number | null
  field_id?: number | null
  object_type: string
  candidate_type: string
  candidate_value: string
  confidence: number
  reasoning?: string | null
  status: string
  evidence_payload: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
  decided_at?: string | null
}

export interface SourceField {
  id: number
  project_id: number
  instance_id: number
  asset_id: number
  field_key: string
  field_name: string
  display_name: string
  physical_type: string
  nullable: boolean
  ordinal_position: number
  status: string
  is_partition_key: boolean
  is_primary_key_candidate: boolean
  is_time_field_candidate: boolean
  last_seen_at?: string | null
  latest_profile?: SourceFieldProfile | null
  profiles?: SourceFieldProfile[]
  candidates: SemanticCandidate[]
}

export interface SourceChangeEvent {
  id: number
  instance_id: number
  asset_id?: number | null
  event_type: string
  severity: string
  status: string
  title: string
  summary?: string | null
  recommended_action?: string | null
  detail_payload: Record<string, unknown>
  brief_payload: Record<string, unknown>
  detected_at?: string | null
  updated_at?: string | null
}

export interface SourceCandidate {
  id: number
  instance_id: number
  asset_id?: number | null
  change_event_id?: number | null
  candidate_type: string
  status: string
  title: string
  summary?: string | null
  recommendation?: string | null
  memory_scope_target: string
  action_payload: Record<string, unknown>
  asset?: SourceAsset | null
  change_event?: SourceChangeEvent | null
  created_at?: string | null
  updated_at?: string | null
  decided_at?: string | null
}

export interface SourceBrief {
  id: number
  instance_id: number
  run_type: string
  status: string
  title?: string | null
  summary?: string | null
  created_at?: string | null
  metrics?: Record<string, unknown>
}

export interface SourceTelemetryPoint {
  sample_at: string
  load_score?: number
  throughput_mb_per_hour?: number
  scan_duration_ms?: number
  failure_rate?: number
  heat_level?: string
  cpu_pct?: number
  memory_pct?: number
  disk_throughput_mb?: number
  network_throughput_mb?: number
  queue_backlog?: number
  health?: string
  role?: string
}

export interface SourceTelemetrySeriesResponse {
  series: Record<string, SourceTelemetryPoint[]>
  latest: Array<Record<string, unknown>>
}

export interface SourceTelemetryOverview {
  summary: {
    instance_count: number
    hot_instances: number
    open_candidates: number
    open_changes: number
  }
  source_load: Array<Record<string, unknown>>
  nodes: Array<Record<string, unknown>>
}

export interface SourceInstanceTelemetry {
  overview?: Record<string, unknown> | null
  source_series: Record<string, SourceTelemetryPoint[]>
  node_series: Record<string, SourceTelemetryPoint[]>
  latest_nodes: Array<Record<string, unknown>>
}

export interface FabricListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  facets: Record<string, unknown>
}

export interface FabricSourceProfile {
  id: number
  source_name: string
  source_type: string
  status: string
  heat_level: string
  total_objects: number
  total_rows: number
  total_columns: number
  estimated_bytes: number
  key_candidates: string[]
  time_candidates: string[]
  domain_candidates: string[]
  update_mode: string
  refresh_cadence: string
  freshness_hours?: number | null
  last_scan_status?: string | null
  last_scanned_at?: string | null
  materialization_reason: string
  top_objects: Array<{
    name: string
    rows: number
    heat_level: string
  }>
}

export interface FabricUpdateSemantic {
  source_id: number
  source_name: string
  source_type: string
  update_mode: string
  refresh_cadence: string
  confidence: number
  planner_strategy: string
  key_candidates: string[]
  time_candidates: string[]
  freshness_hours?: number | null
  reasoning: string[]
  recommended_actions: string[]
  last_scanned_at?: string | null
}

export interface FabricSemanticDomain {
  domain_key: string
  label: string
  score: number
  source_count: number
  memory_count: number
  contract_count: number
  evidences: string[]
}

export interface FabricSemanticDomainResponse {
  items: FabricSemanticDomain[]
  summary: {
    domain_count: number
    top_domain: string
  }
}

export interface FabricQueryPlan {
  question: string
  latency_target_ms: number
  domain: {
    domain_key: string
    label: string
    evidences: string[]
  }
  strategy: string
  rationale: string
  matched_sources: Array<{
    id: number
    source_name: string
    source_type: string
    status: string
    heat_level: string
  }>
  matched_memories: Array<{
    id: number
    title: string
    module: string
    status: string
  }>
  matched_contracts: Array<{
    id: number
    contract_name: string
    event_code: string
    serving_status: string
  }>
  steps: Array<{
    step: number
    title: string
    detail: string
  }>
}

export interface FabricQueryIntentRecord {
  id: number
  trace_id: string
  question: string
  intent_type: string
  domain?: string | null
  time_scope?: string | null
  dimensions: string[]
  metrics: string[]
  operation_mode: string
  latency_expectation: string
  candidate_paths: string[]
  created_at?: string | null
}

export interface FabricQueryPlanRecord {
  id: number
  trace_id: string
  intent_id: number
  selected_path: string
  plan_status: string
  engine_strategy?: string | null
  rationale: string
  plan_payload: Record<string, unknown>
  matched_payload: Record<string, unknown>
  created_at?: string | null
}

export interface FabricContextRef {
  id: number | string
  object_type: string
  label?: string | null
  reason?: string | null
  evidence_mode?: string | null
  priority?: number | null
}

export interface FabricQueryRun {
  id: number
  trace_id: string
  run_key: string
  intent_id: number
  plan_id: number
  execution_mode: string
  status: string
  current_stage?: string | null
  engine_family?: string | null
  result_summary?: string | null
  error_message?: string | null
  metrics_payload: Record<string, unknown>
  submitted_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at?: string | null
}

export interface FabricExecutionStage {
  id: number
  run_id: number
  stage_no: number
  stage_key: string
  title: string
  goal: string
  engine_key?: string | null
  status: string
  planning_payload: Record<string, unknown>
  metrics_payload: Record<string, unknown>
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
}

export interface FabricExecutedSQL {
  id: number
  run_id: number
  stage_id?: number | null
  engine_key: string
  execution_role: string
  status: string
  sql_hash?: string | null
  sql_text: string
  metrics_payload: Record<string, unknown>
  submitted_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface FabricMaterializationArtifact {
  id: number
  trace_id: string
  plan_id?: number | null
  run_id?: number | null
  artifact_name: string
  artifact_type: string
  status: string
  heat_level: string
  engine_key?: string | null
  storage_strategy?: string | null
  retention_policy?: string | null
  reason: string
  artifact_payload: Record<string, unknown>
  last_promoted_at?: string | null
  last_accessed_at?: string | null
  expires_at?: string | null
  updated_at?: string | null
}

export interface FabricQuerySubmission {
  trace_id: string
  intent: FabricQueryIntentRecord
  plan: FabricQueryPlanRecord
  run: FabricQueryRun
  artifacts: FabricMaterializationArtifact[]
}

export interface FabricQueryRunListItem extends FabricQueryRun {
  question: string
  intent_type: string
  domain?: string | null
  selected_path: string
}

export interface FabricQueryRunDetail {
  trace_id: string
  intent: FabricQueryIntentRecord | null
  plan: FabricQueryPlanRecord | null
  run: FabricQueryRun
  stages: FabricExecutionStage[]
  prepared_sql: FabricExecutedSQL[]
  artifacts: FabricMaterializationArtifact[]
}

export interface FabricTraceResponse {
  trace_id: string
  intent: FabricQueryIntentRecord | null
  plan: FabricQueryPlanRecord | null
  runs: FabricQueryRun[]
  stages: Record<string, FabricExecutionStage[]>
  prepared_sql: Record<string, FabricExecutedSQL[]>
  artifacts: FabricMaterializationArtifact[]
}

export interface FabricMaterialization {
  id: string
  artifact_type: string
  artifact_name: string
  source_name: string
  heat_level: string
  status: string
  acceleration_tier: string
  latency_target_ms: number
  reason: string
  updated_at?: string | null
}

export interface FabricTelemetryOverview {
  summary: {
    source_count: number
    hot_sources: number
    scan_failures: number
    running_pipelines: number
    open_alerts: number
  }
  source_load: Array<{
    source_id: number
    source_name: string
    heat_level: string
    freshness_hours?: number | null
    throughput_mb_per_hour: number
    load_score: number
    status: string
  }>
  cluster_nodes: Array<{
    node_name: string
    role: string
    health: string
    cpu_pct: number
    memory_pct: number
    disk_throughput_mb: number
    derived: boolean
  }>
  alerts: Array<{
    id: number
    severity: string
    status: string
    title: string
    source_type: string
    source_id: string
  }>
}

export interface P0OverviewResponse {
  summary: {
    observation_sources: number
    observed_events: number
    inference_queue: number
    published_contracts: number
  }
  observation: {
    total_logs: number
    events_7d: number
    active_channels: number
    top_sources: P0SourceStat[]
    source_profiles: P0SourceProfile[]
    unknown_signals: P0UnknownSignal[]
  }
  inference: {
    total_proposals: number
    pending_proposals: number
    high_confidence_pending: number
    ai_generated_pending: number
    unmapped_pending: number
    avg_confidence: number
    top_proposals: P0ProposalItem[]
    candidates: P0InferenceCandidate[]
  }
  governance: {
    pending_reviews: number
    approved_rules: number
    rejected_rules: number
    decision_summary: {
      pending: number
      approved: number
      rejected: number
    }
    queue: P0GovernanceQueueItem[]
    recent_decisions: P0DecisionItem[]
  }
  contract: {
    active_contracts: number
    approved_rules: number
    artifacts: P0ContractArtifact[]
    recent_contracts: P0ContractItem[]
  }
}

export interface SettingsGeneral {
  project_id: number
  tenant_id: number
  name: string
  description?: string | null
  tags: string[]
  default_domain?: string | null
  updated_at: string
}

export interface SettingsMember {
  user_id: number
  email: string
  name: string
  project_role: string
  tenant_role?: string | null
  joined_at?: string | null
  auth_provider: string
  is_active: boolean
}

export interface SettingsPendingInvitation {
  id: number
  email: string
  role: string
  status: string
  expires_at: string
  created_at: string
  updated_at: string
}

export interface SettingsMembersResponse {
  items: SettingsMember[]
  pending_invitations: SettingsPendingInvitation[]
}

export interface SettingsIntegrationItem {
  integration_type: 'LLM' | 'KAFKA' | 'FLINK' | 'QDRANT' | string
  enabled: boolean
  config: Record<string, unknown>
  has_stored_secret: boolean
  last_test?: {
    status: 'SUCCESS' | 'FAILURE' | string
    message: string
    tested_at?: string | null
  } | null
  updated_at?: string | null
}

export interface SettingsIntegrationTestResult {
  integration_type: string
  status: 'SUCCESS' | 'FAILURE' | string
  message: string
}

export interface SettingsSecurity {
  tenant_id: number
  sso_enabled: boolean
  mfa_required: boolean
  password_policy: {
    min_length: number
    require_upper: boolean
    require_lower: boolean
    require_number: boolean
    require_symbol: boolean
  }
  audit_policy: {
    retention_days: number
    export_requires_approval: boolean
    max_exports_per_day: number
  }
  updated_at: string
}

export interface SettingsOverviewResponse {
  general: SettingsGeneral
  members: SettingsMembersResponse
  integrations: SettingsIntegrationItem[]
  security: SettingsSecurity
  permissions: {
    can_manage_general: boolean
    can_manage_members: boolean
    can_manage_integrations: boolean
    can_manage_security: boolean
  }
}

export interface ExploreSourceSummary {
  source_system: string
  asset_count: number
  database_count: number
}

export interface ExploreCatalogColumn {
  name: string
  query_name: string
  type: string
}

export interface ExploreCatalogAsset {
  id: number
  name: string
  asset_type: string
  object_name: string
  domain: string
  owner?: string | null
  status: string
  virtual_table: string
  column_count: number
  columns: ExploreCatalogColumn[]
}

export interface ExploreCatalogDatabase {
  database_name: string
  assets: ExploreCatalogAsset[]
}

export interface ExploreCatalogSourceNode {
  source_system: string
  databases: ExploreCatalogDatabase[]
}

export interface ExploreAssetProfileColumn {
  name: string
  query_name: string
  type: string
  required: boolean
  description?: string | null
}

export interface ExploreAssetProfile {
  asset: {
    id: number
    name: string
    asset_type: string
    source_system: string
    database_name?: string | null
    object_name: string
    domain: string
    owner?: string | null
    status: string
    virtual_table: string
  }
  columns: ExploreAssetProfileColumn[]
  sample_rows: Array<Record<string, unknown>>
  suggested_queries: Array<{
    title: string
    sql: string
  }>
}

export interface ExploreQueryResponse {
  columns: string[]
  rows: Array<Record<string, unknown>>
  total_rows: number
  page: number
  page_size: number
  total_pages: number
  execution_ms: number
  guidance: string
}

export interface ExploreExportResponse {
  format: 'csv' | 'json' | string
  filename: string
  mime_type: string
  row_count: number
  content: string
}

export interface ExplorePrefillResponse {
  title: string
  description: string
  sql: string
}

export interface InfrastructureKafkaCluster {
  cluster_id: string
  environment: string
  health_status: string
  version: string
  controller: string
  broker_count: number
  healthy_brokers: number
  topic_count: number
  warning_count: number
}

export interface InfrastructureKafkaTopic {
  pipeline_id: number
  topic_name: string
  event_code: string
  status: string
  environment: string
  cluster_id: string
  partitions: number
  replication_factor: number
  retention_hours: number
  estimated_backlog: number
  alert_count: number
  catalog_asset_id?: number | null
  links: {
    pipelines?: string | null
    catalog?: string | null
    explore_prefill?: string | null
  }
}

export interface InfrastructureFlinkCluster {
  cluster_id: string
  environment: string
  health_status: string
  version: string
  taskmanagers_total: number
  taskmanagers_healthy: number
  slots_total: number
  slots_used: number
  checkpoint_health: string
  job_count: number
}

export interface InfrastructureFlinkJob {
  pipeline_id: number
  job_name: string
  job_id: string
  state: string
  pipeline_status: string
  event_code: string
  environment: string
  cluster_id: string
  retry_count: number
  last_sync_at?: string | null
  alert_count: number
  scheduler_dag_ids: number[]
  latest_scheduler_state?: string | null
  links: {
    pipelines?: string | null
    scheduler?: string | null
    explore_prefill?: string | null
  }
}

export interface InfrastructureStorageSystem {
  source_system: string
  environment: string
  cluster_id: string
  asset_count: number
  used_gb: number
  capacity_gb: number
  usage_rate: number
}

export interface InfrastructureStoragePath {
  path: string
  source_system: string
  database_name: string
  environment: string
  cluster_id: string
  asset_count: number
  used_gb: number
  capacity_gb: number
  usage_rate: number
  hot_level: string
  related_pipeline_alert_count: number
  sample_assets: Array<{
    id: number
    name: string
    asset_type: string
    object_name: string
  }>
  links: {
    catalog?: string | null
    explore_prefill?: string | null
  }
}

export interface InfrastructureAlertItem {
  id: number
  source_type: string
  source_id: string
  severity: string
  status: string
  title: string
  description: string
  environment: string
  cluster_id?: string | null
  created_at: string
  links: {
    pipelines?: string | null
    data_quality?: string | null
    scheduler?: string | null
    explore_prefill?: string | null
  }
}

export interface InfrastructureOverviewResponse {
  filters: {
    selected_environment?: string | null
    selected_cluster?: string | null
    available_environments: string[]
    available_clusters: string[]
  }
  summary: {
    kafka_clusters: number
    kafka_topics: number
    flink_clusters: number
    flink_jobs: number
    storage_systems: number
    open_alerts: number
  }
  kafka: {
    clusters: InfrastructureKafkaCluster[]
    topics: InfrastructureKafkaTopic[]
    totals: {
      topic_count: number
      running_topics: number
      failed_topics: number
      open_alerts: number
      estimated_backlog: number
    }
  }
  flink: {
    clusters: InfrastructureFlinkCluster[]
    jobs: InfrastructureFlinkJob[]
    totals: {
      job_count: number
      running_jobs: number
      failed_jobs: number
      open_alerts: number
    }
  }
  storage: {
    overview: {
      capacity_total_gb: number
      used_gb: number
      usage_rate: number
      hot_path_count: number
    }
    systems: InfrastructureStorageSystem[]
    key_paths: InfrastructureStoragePath[]
  }
  alerts: {
    open_count: number
    critical_count: number
    high_count: number
    by_source: Array<{ source_type: string; count: number }>
    recent: InfrastructureAlertItem[]
  }
  collected_at: string
}

export interface MonitoringTrendPoint {
  timestamp: string
  qps: number
  latency_ms: number
  failure_rate: number
  alert_count: number
}

export interface MonitoringModuleHealth {
  module: string
  status: 'GREEN' | 'YELLOW' | 'RED' | string
  score: number
  open_alerts: number
  critical_alerts: number
  last_alert_at?: string | null
}

export interface MonitoringOverviewResponse {
  filters: {
    selected_modules: string[]
    available_modules: string[]
    window_minutes: number
    bucket_count: number
    bucket_seconds: number
  }
  summary: {
    open_alerts: number
    critical_alerts: number
    acknowledged_alerts: number
    resolved_alerts: number
    total_alerts: number
  }
  trends: MonitoringTrendPoint[]
  module_health: MonitoringModuleHealth[]
  business_metrics: {
    total_pipelines: number
    running_pipelines: number
    failed_pipelines: number
    dq_rule_failures: number
    scheduler_failed_runs: number
    governance_checks: number
  }
  collected_at: string
}

export interface MonitoringAlertListItem {
  id: number
  source_type: string
  source_id: string
  source_module: string
  severity: string
  title: string
  description: string
  status: string
  claimed_by?: string | null
  claimed_at?: string | null
  resolved_at?: string | null
  last_note?: string | null
  created_at: string
  updated_at: string
  links: {
    module: string
    module_route: string
    entity: {
      source_type: string
      source_id: string
    }
    explore_prefill?: string | null
  }
}

export interface MonitoringAlertListResponse {
  items: MonitoringAlertListItem[]
  total: number
  limit: number
  offset: number
  facets: {
    modules: Array<{ module: string; count: number }>
    severities: Array<{ severity: string; count: number }>
    statuses: Array<{ status: string; count: number }>
  }
}

export interface MonitoringAlertDetailResponse {
  alert: MonitoringAlertListItem
  metadata: {
    tenant_id?: number | null
    project_id: number
    source_module: string
    source_type: string
    source_id: string
  }
  context_metrics: {
    window_minutes: number
    bucket_minutes: number
    timeline: Array<{
      from: string
      to: string
      qps: number
      failure_rate: number
      latency_ms: number
    }>
  }
  related_links: MonitoringAlertListItem['links']
  history: Array<{
    id: number
    action: string
    actor: string
    actor_id: string
    note?: string | null
    payload: Record<string, unknown>
    created_at: string
  }>
}

export interface MonitoringAlertActionResponse {
  alert: MonitoringAlertListItem
  latest_action: {
    id: number
    action: string
    actor: string
    actor_id: string
    note?: string | null
    payload: Record<string, unknown>
    created_at: string
  }
}

export interface CollaborationWorkflowItem {
  id: number
  project_id: number
  tenant_id?: number | null
  workflow_type: string
  source_type: string
  source_id: string
  title: string
  description?: string | null
  status: string
  priority: string
  initiator: string
  initiator_id: string
  initiator_user_id?: number | null
  current_assignee_user_id?: number | null
  current_assignee_role?: string | null
  started_at?: string | null
  completed_at?: string | null
  context_payload: Record<string, unknown>
  outcome: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CollaborationTaskItem {
  id: number
  workflow_id: number
  title: string
  description?: string | null
  action_type: string
  status: string
  priority: string
  assignee_user_id?: number | null
  assignee_role?: string | null
  due_at?: string | null
  completed_at?: string | null
  completed_by?: string | null
  created_at: string
  updated_at: string
}

export interface CollaborationCommentItem {
  id: number
  author: string
  author_id: string
  content: string
  mentions: string[]
  created_at: string
}

export interface CollaborationActionHistoryItem {
  id: number
  action: string
  actor: string
  actor_id: string
  note?: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface CollaborationOverviewResponse {
  summary: {
    total_workflows: number
    open_todos: number
    initiated_count: number
    status_counts: Record<string, number>
  }
  my_todos: CollaborationTaskItem[]
  initiated_workflows: CollaborationWorkflowItem[]
  recent_workflows: CollaborationWorkflowItem[]
}

export interface CollaborationWorkflowListResponse {
  items: Array<CollaborationWorkflowItem & { open_task_count: number; is_my_todo: boolean }>
  total: number
  limit: number
  offset: number
}

export interface CollaborationWorkflowDetailResponse {
  workflow: CollaborationWorkflowItem
  tasks: CollaborationTaskItem[]
  comments: CollaborationCommentItem[]
  action_history: CollaborationActionHistoryItem[]
  linked_object: {
    source_type: string
    source_id: string
    route: string
  }
  latest_action?: CollaborationActionHistoryItem
  backwrite?: Record<string, unknown>
}

export interface KnowledgeTemplateItem {
  key: string
  doc_type: string
  module: string
  title: string
  summary: string
  content?: string
}

export interface KnowledgeRelatedObjectItem {
  source_type: string
  source_id: string
  label?: string | null
  module?: string | null
  module_route?: string | null
  exists?: boolean | null
}

export interface KnowledgeDocumentItem {
  id: number
  project_id: number
  tenant_id?: number | null
  doc_type: string
  module: string
  knowledge_level: string
  title: string
  summary?: string | null
  content: string
  preview: string
  format: string
  status: string
  tags: string[]
  related_objects: KnowledgeRelatedObjectItem[]
  object_refs: Array<Record<string, unknown>>
  fact_refs: Array<Record<string, unknown>>
  fact_ref_count: number
  has_fact_refs: boolean
  author: string
  author_id: string
  author_user_id?: number | null
  last_editor: string
  last_editor_id: string
  last_editor_user_id?: number | null
  version_no: number
  comment_count: number
  published_at?: string | null
  archived_at?: string | null
  meta_payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface KnowledgeDocumentVersionItem {
  id: number
  document_id: number
  project_id: number
  version_no: number
  action: string
  title: string
  summary?: string | null
  content: string
  tags: string[]
  related_objects: KnowledgeRelatedObjectItem[]
  editor: string
  editor_id: string
  editor_user_id?: number | null
  change_note?: string | null
  snapshot: Record<string, unknown>
  created_at: string
}

export interface KnowledgeDocumentCommentItem {
  id: number
  document_id: number
  author: string
  author_id: string
  author_user_id?: number | null
  content: string
  mentions: string[]
  created_at: string
}

export interface KnowledgeOverviewResponse {
  summary: {
    total_docs: number
    published_docs: number
    draft_docs: number
    archived_docs: number
    updated_docs_7d: number
    comments_7d: number
  }
  directory: {
    modules: Record<string, number>
    doc_types: Record<string, number>
    statuses: Record<string, number>
    top_tags: Array<[string, number]>
  }
  recent_documents: KnowledgeDocumentItem[]
  my_documents: KnowledgeDocumentItem[]
  templates: KnowledgeTemplateItem[]
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocumentItem[]
  total: number
  limit: number
  offset: number
  facets: {
    modules: string[]
    doc_types: string[]
    knowledge_levels: string[]
    statuses: string[]
    tags: string[]
  }
}

export interface KnowledgeDocumentDetailResponse {
  document: KnowledgeDocumentItem
  version_history: KnowledgeDocumentVersionItem[]
  comments: KnowledgeDocumentCommentItem[]
  related_documents: KnowledgeDocumentItem[]
  restored_from?: KnowledgeDocumentVersionItem
}

export interface AssistantChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantChatCitation {
  type: string
  id: number | string
  label: string
  kind?: 'FACT' | 'CANDIDATE' | 'KNOWLEDGE' | 'BRIEF' | 'ASSET' | string
  object_type?: string
  status?: string
  evidence_mode?: string
}

export interface AssistantRuntimeConfigPayload {
  api_key?: string
  base_url?: string
  model?: string
}

export interface AssistantChatResponse {
  answer: string
  mode: 'llm' | 'fallback' | string
  citations: AssistantChatCitation[]
  suggestions: string[]
  query_trace?: FabricQuerySubmission
}

export interface CostUsageResourceItem {
  project_id: number
  project_name: string
  module: string
  resource_type: string
  resource_name: string
  source_type: string
  source_id: string
  route: string
  total_cost: number
  usage_units: number
  cost_components: {
    compute: number
    storage: number
    network: number
    llm: number
  }
  updated_at?: string | null
  driver: string
  related_context: Record<string, unknown>
  optimize_actions: Array<{
    action: string
    reason: string
    target_route: string
    estimated_saving: number
  }>
}

export interface CostUsageOverviewResponse {
  summary: {
    scope: string
    project_count: number
    total_cost: number
    total_usage_units: number
    currency: string
    window: {
      date_from: string
      date_to: string
      granularity: string
    }
    cost_components: {
      compute: number
      storage: number
      network: number
      llm: number
    }
  }
  trend: Array<{
    timestamp: string
    total_cost: number
    compute_cost: number
    storage_cost: number
    network_cost: number
    llm_cost: number
    usage_units: number
  }>
  module_breakdown: Array<{
    module: string
    cost: number
    percentage: number
  }>
  resource_type_breakdown: Array<{
    resource_type: string
    cost: number
    percentage: number
  }>
  project_ranking: Array<{
    project_id: number
    project_name: string
    cost: number
    delta_7d: number
    trend: 'UP' | 'DOWN' | 'FLAT' | string
  }>
  top_resources: CostUsageResourceItem[]
  optimization_candidates: Array<{
    resource: CostUsageResourceItem
    recommended_action: {
      action: string
      reason: string
      target_route: string
      estimated_saving: number
    }
    potential_saving: number
  }>
  filters: {
    modules: string[]
    resource_types: string[]
    projects: Array<{ id: number; name: string }>
    scopes: string[]
  }
}

export interface CostUsageResourceListResponse {
  items: CostUsageResourceItem[]
  total: number
  limit: number
  offset: number
  facets: {
    modules: string[]
    resource_types: string[]
    projects: string[]
  }
}

export interface CostUsageResourceDetailResponse {
  resource: CostUsageResourceItem
  trend: CostUsageOverviewResponse['trend']
  window: {
    date_from: string
    date_to: string
    granularity: string
  }
  comparison: {
    module_average_cost: number
    module_rank: number
    module_size: number
  }
  navigation: {
    module_route: string
    module: string
  }
  optimization_actions: CostUsageResourceItem['optimize_actions']
}

export type SandboxExperimentType =
  | 'EVENT_EXPERIMENT'
  | 'DQ_RULE_EXPERIMENT'
  | 'PIPELINE_EXPERIMENT'
  | 'QUERY_EXPERIMENT'

export type SandboxExperimentStatus = 'DRAFT' | 'RUNNING' | 'COMPLETED' | 'PROMOTED' | 'CANCELLED'

export interface SandboxOptionItem {
  id: string
  label: string
  [key: string]: unknown
}

export interface SandboxOptionsResponse {
  experiment_types: SandboxExperimentType[]
  source_types: string[]
  source_options: {
    TRACKING_EVENT: SandboxOptionItem[]
    DATA_QUALITY_RULE: SandboxOptionItem[]
    PIPELINE: SandboxOptionItem[]
    QUERY_TEMPLATE: SandboxOptionItem[]
  }
}

export interface SandboxExperimentRunItem {
  id: number
  experiment_id: number
  project_id: number
  run_no: number
  status: string
  triggered_by: string
  triggered_by_id: string
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
  run_context: Record<string, unknown>
  report_payload: Record<string, unknown>
  recommendation_payload: Record<string, unknown>
  created_at: string
}

export interface SandboxExperimentItem {
  id: number
  project_id: number
  tenant_id?: number | null
  experiment_type: SandboxExperimentType
  title: string
  description?: string | null
  status: SandboxExperimentStatus
  source_type: string
  source_id: string
  sandbox_source_type?: string | null
  sandbox_source_id?: string | null
  source_route: string
  created_by: string
  created_by_id: string
  updated_by: string
  updated_by_id: string
  config_payload: Record<string, unknown>
  baseline_payload: Record<string, unknown>
  best_candidate_payload: Record<string, unknown>
  conclusion: Record<string, unknown>
  promote_target_type?: string | null
  promote_target_id?: string | null
  promoted_at?: string | null
  created_at: string
  updated_at: string
}

export interface SandboxOverviewResponse {
  summary: {
    total_experiments: number
    draft_count: number
    running_count: number
    completed_count: number
    promoted_count: number
    cancelled_count: number
    runs_7d: number
  }
  status_counts: Record<string, number>
  type_counts: Record<string, number>
  recent_experiments: Array<SandboxExperimentItem & { latest_run?: SandboxExperimentRunItem | null }>
  pending_promotion: SandboxExperimentItem[]
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    entity_id: string
    summary: string
  }>
}

export interface SandboxExperimentListResponse {
  items: Array<SandboxExperimentItem & { latest_run?: SandboxExperimentRunItem | null }>
  total: number
  limit: number
  offset: number
  facets: {
    statuses: string[]
    experiment_types: string[]
    source_types: string[]
  }
}

export interface SandboxExperimentDetailResponse {
  experiment: SandboxExperimentItem
  runs: SandboxExperimentRunItem[]
  latest_run?: SandboxExperimentRunItem | null
  navigation: {
    module_route: string
    source_type: string
    source_id: string
  }
}

export interface SandboxRunResponse {
  experiment: SandboxExperimentItem
  run: SandboxExperimentRunItem
  recommendation: Record<string, unknown>
}

export interface SandboxPromoteResponse {
  experiment: SandboxExperimentItem
  promoted_candidate: Record<string, unknown>
  promotion_target: {
    target_type: string
    target_id: string
    route: string
  }
}

export interface IntegrationHubUsageScenario {
  module: string
  calls: number
  success_calls: number
  failure_calls: number
  last_used_at?: string | null
}

export interface IntegrationHubHealth {
  status: 'UNKNOWN' | 'HEALTHY' | 'WARNING' | 'UNHEALTHY' | string
  last_heartbeat_at?: string | null
  total_calls_7d: number
  success_calls_7d: number
  failure_calls_7d: number
  success_rate_7d: number
  error_code_distribution: Array<{ error_code: string; count: number }>
}

export interface IntegrationHubItem {
  integration_type: string
  category: string
  enabled: boolean
  config: Record<string, unknown>
  has_stored_secret: boolean
  last_test?: {
    status: 'SUCCESS' | 'FAILURE' | string
    message: string
    tested_at?: string | null
  } | null
  usage_scenarios: IntegrationHubUsageScenario[]
  health: IntegrationHubHealth
  recent_calls: Array<{
    id: number
    caller_module: string
    action: string
    status: 'SUCCESS' | 'FAILURE' | string
    error_code?: string | null
    error_message?: string | null
    latency_ms: number
    actor: string
    created_at: string
  }>
  created_at?: string | null
  updated_at?: string | null
}

export interface IntegrationHubOverviewResponse {
  summary: {
    configured_count: number
    enabled_count: number
    healthy_count: number
    unhealthy_count: number
    coverage_ratio: number
  }
  category_breakdown: Array<{ category: string; count: number }>
  top_failures: Array<{ error_code: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    integration_type: string
    summary: string
  }>
  items: IntegrationHubItem[]
}

export interface IntegrationHubListResponse {
  items: IntegrationHubItem[]
  total: number
  limit: number
  offset: number
  facets: {
    types: string[]
    categories: string[]
    health_statuses: string[]
  }
}

export interface IntegrationHubDetailResponse {
  integration: IntegrationHubItem
  template: Record<string, unknown>
}

export interface IntegrationHubTestResponse {
  integration_type: string
  status: 'SUCCESS' | 'FAILURE' | string
  message: string
  error_code?: string | null
  latency_ms: number
}

export interface IntegrationHubInvokeResponse {
  status: 'SUCCESS' | 'FAILURE' | string
  integration_type: string
  caller_module: string
  action: string
  error_code?: string | null
  message?: string
  alert_id?: number
  external_request_id?: string
  latency_ms?: number
}

export interface AccessTenantRoleBinding {
  id?: number
  tenant_id: number
  role: string
  updated_at?: string | null
}

export interface AccessProjectRoleBinding {
  id?: number
  project_id: number
  project_name: string
  role: string
  updated_at?: string | null
}

export interface AccessUserItem {
  user_id: number
  email: string
  name: string
  status: 'ACTIVE' | 'INACTIVE' | string
  organization?: string | null
  last_login_at?: string | null
  highest_role?: string | null
  tenant_roles: AccessTenantRoleBinding[]
  project_roles: AccessProjectRoleBinding[]
  auth_provider?: string
  created_at?: string | null
  updated_at?: string | null
}

export interface AccessOverviewResponse {
  summary: {
    total_users: number
    active_users: number
    inactive_users: number
    pending_invitations: number
    admin_users: number
    role_templates: number
  }
  role_distribution: Array<{ role: string; count: number }>
  status_distribution: Array<{ status: string; count: number }>
  recent_security_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    entity_type: string
    entity_id: string
    summary: string
  }>
}

export interface AccessUserListResponse {
  items: AccessUserItem[]
  total: number
  limit: number
  offset: number
  facets: {
    roles: Array<{ role: string; count: number }>
    statuses: Array<{ status: string; count: number }>
  }
}

export interface AccessUserDetailResponse {
  user: AccessUserItem
  audit_summary: {
    recent_actions: Array<{
      id: number
      timestamp: string
      action: string
      entity_type: string
      entity_id: string
      summary: string
    }>
    top_actions: Array<{ action: string; count: number }>
  }
  effective_permission_profiles: Array<{
    role: string
    template_key: string
    template_name?: string | null
    module_count: number
    is_active: boolean
  }>
}

export interface AccessInviteResponse {
  mode: 'member_updated' | 'invitation_sent' | string
  member?: AccessUserItem | null
  pending_invitation?: {
    id: number
    email: string
    tenant_id: number
    project_id: number
    project_role: string
    tenant_role: string
    status: string
    expires_at: string
    created_at: string
  } | null
  delivery: {
    channel: string
    status: string
  }
}

export interface AccessUserStatusResponse {
  user_id: number
  email: string
  is_active: boolean
  updated_at?: string | null
}

export interface AccessRoleTemplateItem {
  template_key: string
  name: string
  description?: string | null
  permission_matrix: {
    modules: Record<string, string[]>
  }
  is_active: boolean
  is_system: boolean
  source: 'SYSTEM' | 'TENANT_OVERRIDE' | 'TENANT_CUSTOM' | string
  template_id?: number | null
  updated_at?: string | null
}

export interface AccessRoleTemplateListResponse {
  items: AccessRoleTemplateItem[]
  total: number
}

export interface AccessEvaluateResponse {
  allow: boolean
  reason: string
  effective_role?: string | null
  template?: {
    template_key: string
    name?: string | null
    source?: string
  }
  module: string
  action: string
}

export interface PolicyRuleItem {
  id: number
  rule_type: string
  name: string
  description?: string | null
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string
  status: 'DRAFT' | 'ACTIVE' | 'INACTIVE' | 'ARCHIVED' | string
  scope: {
    scope_type: 'GLOBAL' | 'TENANT' | 'PROJECT' | 'DOMAIN' | string
    scope_value?: string | null
    project_id?: number | null
    project_name?: string | null
  }
  conditions_payload: Record<string, unknown>
  actions_payload: Record<string, unknown>
  content_payload: Record<string, unknown>
  prompt_text?: string | null
  version_no: number
  created_by: string
  updated_by: string
  created_at?: string | null
  updated_at?: string | null
}

export interface PolicyRuleVersionItem {
  id: number
  version_no: number
  change_note?: string | null
  snapshot_payload: Record<string, unknown>
  created_by: string
  created_at?: string | null
}

export interface PolicyOverviewResponse {
  summary: {
    total_rules: number
    active_rules: number
    draft_rules: number
    inactive_rules: number
    archived_rules: number
    project_scoped_rules: number
  }
  status_distribution: Array<{ status: string; count: number }>
  type_distribution: Array<{ rule_type: string; count: number }>
  scope_distribution: Array<{ scope_type: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    rule_id: string
    summary: string
  }>
}

export interface PolicyTemplateItem {
  key: string
  rule_type: string
  name: string
  description?: string | null
  severity: string
  scope_type: string
  conditions_payload: Record<string, unknown>
  actions_payload: Record<string, unknown>
  content_payload: Record<string, unknown>
}

export interface PolicyTemplateListResponse {
  items: PolicyTemplateItem[]
  total: number
}

export interface PolicyRuleListResponse {
  items: PolicyRuleItem[]
  total: number
  limit: number
  offset: number
  facets: {
    statuses: Array<{ status: string; count: number }>
    rule_types: Array<{ rule_type: string; count: number }>
    scope_types: Array<{ scope_type: string; count: number }>
    severities: Array<{ severity: string; count: number }>
  }
}

export interface PolicyRuleDetailResponse {
  rule: PolicyRuleItem
  versions: PolicyRuleVersionItem[]
}

export interface PolicyEvaluateResponse {
  module: string
  action: string
  decision: 'PASS' | 'WARN' | 'REJECT' | string
  matched_rule_count: number
  violation_count: number
  matched_rules: Array<{
    rule_id: number
    name: string
    rule_type: string
    severity: string
    decision: string
    version_no: number
  }>
  violations: Array<{
    rule_id: number
    rule_name: string
    decision: string
    violations: string[]
  }>
  recommendations: string[]
}

export interface ReleaseChangeRiskAssessment {
  auto?: {
    risk_score: number
    risk_level: string
    factors: string[]
  }
  manual?: {
    review_note?: string | null
    reviewed: boolean
  }
  final?: {
    risk_score: number
    risk_level: string
    factors: string[]
  }
}

export interface ReleaseChangeItem {
  id: number
  change_type: string
  source: {
    source_type: string
    source_id: string
    route: string
  }
  title: string
  description?: string | null
  priority: string
  status: string
  impact_scope: Record<string, unknown>
  diff_payload: Record<string, unknown>
  before_payload: Record<string, unknown>
  after_payload: Record<string, unknown>
  risk_assessment: ReleaseChangeRiskAssessment
  release_plan: Record<string, unknown>
  rollback_plan: Record<string, unknown>
  requested_by: string
  current_approver_role?: string | null
  approved_by?: string | null
  rejected_by?: string | null
  approved_at?: string | null
  rejected_at?: string | null
  scheduled_at?: string | null
  executed_at?: string | null
  completed_at?: string | null
  rolled_back_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ReleaseChangeHistoryItem {
  id: number
  action: string
  actor: string
  note?: string | null
  payload: Record<string, unknown>
  created_at?: string | null
}

export interface ReleaseOverviewResponse {
  summary: {
    total_changes: number
    pending_approval: number
    in_progress: number
    completed: number
    failed: number
    rolled_back: number
    high_risk_open: number
  }
  status_distribution: Array<{ status: string; count: number }>
  type_distribution: Array<{ change_type: string; count: number }>
  priority_distribution: Array<{ priority: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    change_id: string
    summary: string
  }>
}

export interface ReleaseChangeListResponse {
  items: ReleaseChangeItem[]
  total: number
  limit: number
  offset: number
  facets: {
    statuses: Array<{ status: string; count: number }>
    change_types: Array<{ change_type: string; count: number }>
    priorities: Array<{ priority: string; count: number }>
    requesters: Array<{ requested_by: string; count: number }>
  }
}

export interface ReleaseChangeDetailResponse {
  change: ReleaseChangeItem
  history: ReleaseChangeHistoryItem[]
}

export interface ReleaseExecuteResponse {
  change: ReleaseChangeItem
  execution: {
    result: 'SUCCESS' | 'FAILED' | string
    reason?: string
    auto_rollback?: boolean
  }
}

export interface ReportTemplateItem {
  key: string
  kind: 'DASHBOARD' | 'REPORT' | string
  name: string
  scenario?: string | null
  tags: string[]
  layout_payload: Record<string, unknown>
}

export interface ReportDashboardItem {
  id: number
  tenant_id: number
  project_id: number
  kind: 'DASHBOARD' | 'REPORT' | string
  name: string
  description?: string | null
  scenario?: string | null
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED' | string
  template_key?: string | null
  is_personal: boolean
  layout_payload: Record<string, unknown>
  query_payload: Record<string, unknown>
  filter_payload: Record<string, unknown>
  refresh_payload: Record<string, unknown>
  permission_payload: Record<string, unknown>
  tags: string[]
  cached_summary: Record<string, unknown>
  widget_count: number
  created_by: string
  updated_by: string
  published_at?: string | null
  last_data_refresh_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  capabilities: {
    can_view: boolean
    can_edit: boolean
    can_clone: boolean
  }
}

export interface ReportOverviewResponse {
  summary: {
    total_items: number
    dashboards: number
    reports: number
    draft_items: number
    published_items: number
    archived_items: number
    saved_views: number
    template_count: number
  }
  kind_distribution: Array<{ kind: string; count: number }>
  status_distribution: Array<{ status: string; count: number }>
  scenario_distribution: Array<{ scenario: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    dashboard_id: string
    summary: string
  }>
}

export interface ReportTemplateListResponse {
  items: ReportTemplateItem[]
  total: number
}

export interface ReportListResponse {
  items: ReportDashboardItem[]
  total: number
  limit: number
  offset: number
  facets: {
    statuses: Array<{ status: string; count: number }>
    kinds: Array<{ kind: string; count: number }>
    creators: Array<{ creator: string; count: number }>
    scenarios: Array<{ scenario: string; count: number }>
    tags: Array<{ tag: string; count: number }>
  }
}

export interface ReportVersionItem {
  id: number
  dashboard_id: number
  version_no: number
  change_note?: string | null
  snapshot_payload: Record<string, unknown>
  created_by: string
  created_at?: string | null
}

export interface ReportSavedViewItem {
  id: number
  dashboard_id: number
  owner: string
  name: string
  filter_payload: Record<string, unknown>
  layout_override_payload: Record<string, unknown>
  is_default: boolean
  share_token?: string | null
  expires_at?: string | null
  last_export_format?: string | null
  last_export_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ReportDataPayload {
  computed_at: string
  time_window_days: number
  filters: Record<string, unknown>
  widgets: Array<Record<string, unknown>>
  summary: Record<string, unknown>
  cache_key?: string
  cache_ttl_seconds?: number
}

export interface ReportDetailResponse {
  item: ReportDashboardItem
  versions: ReportVersionItem[]
  saved_views: ReportSavedViewItem[]
  applied_filters: Record<string, unknown>
  data_payload?: ReportDataPayload | null
}

export interface MarketplaceProductItem {
  id: number
  tenant_id: number
  project_id: number
  product_key: string
  name: string
  description?: string | null
  domain?: string | null
  category?: string | null
  owner: string
  status: 'DRAFT' | 'PUBLISHED' | 'ARCHIVED' | string
  visibility: 'PROJECT' | 'PRIVATE' | 'ROLE_BASED' | string
  schema_payload: Record<string, unknown>
  asset_ids: number[]
  tags: string[]
  sla_payload: Record<string, unknown>
  usage_payload: Record<string, unknown>
  access_policy_payload: Record<string, unknown>
  published_at?: string | null
  created_by: string
  updated_by: string
  created_at?: string | null
  updated_at?: string | null
  capabilities: {
    can_view: boolean
    can_edit: boolean
  }
}

export interface MarketplaceProductVersionItem {
  id: number
  product_id: number
  version_no: number
  change_note?: string | null
  snapshot_payload: Record<string, unknown>
  created_by: string
  created_at?: string | null
}

export interface MarketplaceSubscriptionItem {
  id: number
  product_id: number
  subscriber: string
  request_reason?: string | null
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED' | 'REVOKED' | string
  decision_note?: string | null
  approved_by?: string | null
  rejected_by?: string | null
  access_token?: string | null
  expires_at?: string | null
  usage_quota_payload: Record<string, unknown>
  last_used_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface MarketplaceOverviewResponse {
  summary: {
    total_products: number
    draft_products: number
    published_products: number
    archived_products: number
    pending_subscriptions: number
    approved_subscriptions: number
    rejected_subscriptions: number
  }
  status_distribution: Array<{ status: string; count: number }>
  domain_distribution: Array<{ domain: string; count: number }>
  subscription_distribution: Array<{ status: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    product_id: string
    summary: string
  }>
}

export interface MarketplaceListResponse {
  items: MarketplaceProductItem[]
  total: number
  limit: number
  offset: number
  facets: {
    statuses: Array<{ status: string; count: number }>
    owners: Array<{ owner: string; count: number }>
    domains: Array<{ domain: string; count: number }>
    tags: Array<{ tag: string; count: number }>
  }
}

export interface MarketplaceDetailResponse {
  product: MarketplaceProductItem
  versions: MarketplaceProductVersionItem[]
  subscriptions: MarketplaceSubscriptionItem[]
  usage_summary: {
    subscription_total: number
    pending: number
    approved: number
    rejected: number
    active_tokens: number
  }
}

export interface IncidentCaseItem {
  id: number
  tenant_id: number
  project_id: number
  runbook_doc_id?: number | null
  source_type: string
  source_id: string
  title: string
  summary?: string | null
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string
  status: 'OPEN' | 'TRIAGED' | 'INVESTIGATING' | 'MITIGATED' | 'RESOLVED' | 'CLOSED' | string
  owner: string
  assignee?: string | null
  context_payload: Record<string, unknown>
  impact_payload: Record<string, unknown>
  resolution_payload: Record<string, unknown>
  started_at?: string | null
  mitigated_at?: string | null
  resolved_at?: string | null
  closed_at?: string | null
  created_by: string
  updated_by: string
  created_at?: string | null
  updated_at?: string | null
  capabilities: {
    can_edit: boolean
  }
}

export interface IncidentTimelineItem {
  id: number
  incident_id: number
  action: string
  actor: string
  note?: string | null
  payload: Record<string, unknown>
  created_at?: string | null
}

export interface IncidentOverviewResponse {
  summary: {
    total_incidents: number
    open_incidents: number
    investigating_incidents: number
    mitigated_incidents: number
    resolved_incidents: number
    closed_incidents: number
    mttr_minutes: number
  }
  status_distribution: Array<{ status: string; count: number }>
  severity_distribution: Array<{ severity: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    incident_id: string
    summary: string
  }>
}

export interface IncidentListResponse {
  items: IncidentCaseItem[]
  total: number
  limit: number
  offset: number
  facets: {
    statuses: Array<{ status: string; count: number }>
    severities: Array<{ severity: string; count: number }>
    owners: Array<{ owner: string; count: number }>
    source_types: Array<{ source_type: string; count: number }>
  }
}

export interface IncidentDetailResponse {
  case: IncidentCaseItem
  timeline: IncidentTimelineItem[]
}

export interface IngestionChannelItem {
  id: number
  tenant_id: number
  project_id: number
  platform: 'WEB' | 'IOS' | 'ANDROID' | 'SERVER' | string
  app_name: string
  environment: 'PROD' | 'STAGING' | 'DEV' | 'TEST' | string
  status: 'ACTIVE' | 'INACTIVE' | string
  app_id: string
  ingest_key: string
  has_ingest_key: boolean
  endpoint_domain: string
  endpoint_path: string
  endpoint: string
  auth_mode: string
  sampling_mode: 'ALL' | 'RATE' | 'NONE' | string
  sampling_rate: number
  switches_payload: Record<string, unknown>
  blocked_events: string[]
  sdk_version: string
  sdk_config_payload: Record<string, unknown>
  quickstart_payload: Record<string, unknown>
  accepted_events_count: number
  rejected_events_count: number
  last_seen_at?: string | null
  last_event_at?: string | null
  created_by: string
  updated_by: string
  created_at?: string | null
  updated_at?: string | null
}

export interface IngestionOverviewResponse {
  summary: {
    total_channels: number
    active_channels: number
    inactive_channels: number
    events_7d: number
    accepted_7d: number
    rejected_7d: number
  }
  platform_breakdown: Array<{ platform: string; count: number }>
  environment_breakdown: Array<{ environment: string; count: number }>
  recent_activity: Array<{
    id: number
    timestamp: string
    actor: string
    action: string
    channel_id: string
    summary: string
  }>
}

export interface IngestionOptionsResponse {
  platforms: string[]
  environments: string[]
  statuses: string[]
  sampling_modes: string[]
  default_switches: Record<string, unknown>
  sdk_download_links: Record<string, Record<string, string>>
}

export interface IngestionChannelListResponse {
  items: IngestionChannelItem[]
  total: number
  limit: number
  offset: number
  facets: {
    platforms: Array<{ platform: string; count: number }>
    environments: Array<{ environment: string; count: number }>
    statuses: Array<{ status: string; count: number }>
  }
}

export interface IngestionChannelDetailResponse {
  channel: IngestionChannelItem
  quickstart: {
    endpoint: string
    headers: Record<string, string>
    sample_payload: Record<string, unknown>
    snippet: string
    downloads: Record<string, string>
  }
  recent_events: Array<{
    id: number
    request_id: string
    event_name: string
    status: 'ACCEPTED' | 'REJECTED' | 'SAMPLED_OUT' | string
    reason_code?: string | null
    reason_message?: string | null
    event_ts?: string | null
    source_ip?: string | null
    sdk_version?: string | null
    created_at?: string | null
  }>
  sdk_download_links: Record<string, string>
}

export interface IngestionChannelMutationResponse {
  channel: IngestionChannelItem
  quickstart: {
    endpoint: string
    headers: Record<string, string>
    sample_payload: Record<string, unknown>
    snippet: string
    downloads: Record<string, string>
  }
  generated_ingest_key?: string
}

export interface IngestionGatewayResponse {
  request_id: string
  status: 'ACCEPTED' | 'REJECTED' | 'SAMPLED_OUT' | string
  reason_code?: string | null
  reason_message?: string | null
  channel: {
    id: number
    app_id: string
    platform: string
    environment: string
  }
  event_log: {
    id: number
    event_name: string
    created_at?: string | null
  }
  alert_id?: number | null
  next_modules: string[]
}

interface RuntimeAuthContext {
  accessToken?: string | null
  tenantId?: number | null
  projectId?: number | null
  apiKey?: string | null
}

const runtimeAuthContext: RuntimeAuthContext = {}

export function setApiAuthContext(next: RuntimeAuthContext) {
  runtimeAuthContext.accessToken = next.accessToken ?? null
  runtimeAuthContext.tenantId = next.tenantId ?? null
  runtimeAuthContext.projectId = next.projectId ?? null
  runtimeAuthContext.apiKey = next.apiKey ?? null
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000',
  timeout: 20000,
})

api.interceptors.request.use((config) => {
  const accessToken = runtimeAuthContext.accessToken
  const projectId = runtimeAuthContext.projectId
  const tenantId = runtimeAuthContext.tenantId

  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
    if (projectId != null) {
      config.headers['X-PROJECT-ID'] = String(projectId)
    }
    if (tenantId != null) {
      config.headers['X-TENANT-ID'] = String(tenantId)
    }
    return config
  }

  config.headers['X-API-KEY'] =
    runtimeAuthContext.apiKey ?? import.meta.env.VITE_API_KEY ?? 'demo-key-001'
  return config
})

let lastGlobalApiError = ''
let lastGlobalApiErrorAt = 0

function extractApiErrorMessage(error: any): string {
  const details = error?.response?.data?.details
  if (typeof details?.message === 'string' && details.message.trim()) {
    return details.message
  }
  if (typeof error?.response?.data?.message === 'string' && error.response.data.message.trim()) {
    return error.response.data.message
  }
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message
  }
  return 'Request failed'
}

function showGlobalApiError(error: any) {
  if (typeof window === 'undefined') return
  const message = extractApiErrorMessage(error)
  const now = Date.now()
  if (message === lastGlobalApiError && now - lastGlobalApiErrorAt < 1200) {
    return
  }
  lastGlobalApiError = message
  lastGlobalApiErrorAt = now
  window.alert(message)
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    showGlobalApiError(error)
    return Promise.reject(error)
  },
)

async function unwrap<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const resp = await promise
  return resp.data.data
}

export const GenesisApi = {
  login: async (payload: { email: string; password: string }): Promise<LoginResponse> =>
    unwrap(api.post<ApiEnvelope<LoginResponse>>('/api/v1/auth/login', payload)),

  register: async (payload: RegisterPayload): Promise<LoginResponse> =>
    unwrap(api.post<ApiEnvelope<LoginResponse>>('/api/v1/auth/register', payload)),

  getMe: async (): Promise<MeResponse> =>
    unwrap(api.get<ApiEnvelope<MeResponse>>('/api/v1/auth/me')),

  updateMe: async (payload: { name: string }): Promise<LoginResponse> =>
    unwrap(api.patch<ApiEnvelope<LoginResponse>>('/api/v1/auth/me', payload)),

  getTenants: async (): Promise<AuthTenant[]> =>
    unwrap(api.get<ApiEnvelope<AuthTenant[]>>('/api/v1/auth/tenants')),

  getProjects: async (tenantId: number): Promise<AuthProject[]> =>
    unwrap(
      api.get<ApiEnvelope<AuthProject[]>>('/api/v1/auth/projects', {
        params: { tenant_id: tenantId },
      }),
    ),

  switchContext: async (payload: { tenant_id: number; project_id: number }): Promise<SwitchContextResponse> =>
    unwrap(api.post<ApiEnvelope<SwitchContextResponse>>('/api/v1/auth/context/switch', payload)),

  generateAnalysisPlan: async (payload: GenerateAnalysisPlanPayload): Promise<AnalysisPlanSummary> =>
    unwrap(api.post<ApiEnvelope<AnalysisPlanSummary>>('/api/v1/analysis-planner/plans/generate', payload)),

  getAnalysisPlans: async (): Promise<AnalysisPlanListResponse> =>
    unwrap(api.get<ApiEnvelope<AnalysisPlanListResponse>>('/api/v1/analysis-planner/plans')),

  getAnalysisPlanDetail: async (planId: number): Promise<AnalysisPlanDetail> =>
    unwrap(api.get<ApiEnvelope<AnalysisPlanDetail>>(`/api/v1/analysis-planner/plans/${planId}`)),

  reviewAnalysisPlan: async (planId: number, payload: ReviewAnalysisPlanPayload): Promise<AnalysisPlanDetail> =>
    unwrap(api.post<ApiEnvelope<AnalysisPlanDetail>>(`/api/v1/analysis-planner/plans/${planId}/review-actions`, payload)),

  getEvents: async (): Promise<TrackingEvent[]> =>
    unwrap(api.get<ApiEnvelope<TrackingEvent[]>>('/api/v1/events/')),

  searchEvents: async (params: {
    q?: string
    domain?: string
    owner?: string
    status?: string
    governance_status?: string
    limit?: number
  }): Promise<TrackingEvent[]> =>
    unwrap(api.get<ApiEnvelope<TrackingEvent[]>>('/api/v1/events/', { params })),

  createEvent: async (payload: {
    code: string
    name: string
    description: string
    properties: Record<string, unknown>
    domain: string
    owner?: string | null
    tags?: string[]
    status?: string
  }): Promise<TrackingEvent> =>
    unwrap(api.post<ApiEnvelope<TrackingEvent>>('/api/v1/events/', payload)),

  updateEvent: async (
    id: number,
    payload: {
      name?: string
      description?: string
      properties?: Record<string, unknown>
      domain?: string
      owner?: string | null
      tags?: string[]
      status?: string
    },
  ): Promise<TrackingEvent> =>
    unwrap(api.patch<ApiEnvelope<TrackingEvent>>(`/api/v1/events/${id}`, payload)),

  getEventDetail: async (id: number): Promise<EventDetailResponse> =>
    unwrap(api.get<ApiEnvelope<EventDetailResponse>>(`/api/v1/events/${id}/detail`)),

  getDataAssets: async (params?: {
    q?: string
    asset_type?: string
    domain?: string
    source_system?: string
    owner?: string
    status?: string
    limit?: number
  }): Promise<DataAsset[]> => unwrap(api.get<ApiEnvelope<DataAsset[]>>('/api/v1/catalog/assets', { params })),

  createDataAsset: async (payload: {
    name: string
    asset_type: string
    source_system: string
    database_name?: string | null
    object_name: string
    domain: string
    owner?: string | null
    status?: string
    tags?: string[]
    description?: string | null
    schema_definition?: Record<string, unknown>
    upstream_asset_ids?: number[]
    downstream_asset_ids?: number[]
  }): Promise<DataAsset> => unwrap(api.post<ApiEnvelope<DataAsset>>('/api/v1/catalog/assets', payload)),

  updateDataAsset: async (
    id: number,
    payload: {
      name?: string
      source_system?: string
      database_name?: string | null
      object_name?: string
      domain?: string
      owner?: string | null
      status?: string
      tags?: string[]
      description?: string | null
      schema_definition?: Record<string, unknown>
      upstream_asset_ids?: number[]
      downstream_asset_ids?: number[]
    },
  ): Promise<DataAsset> => unwrap(api.patch<ApiEnvelope<DataAsset>>(`/api/v1/catalog/assets/${id}`, payload)),

  getDataAssetDetail: async (id: number): Promise<DataAssetDetailResponse> =>
    unwrap(api.get<ApiEnvelope<DataAssetDetailResponse>>(`/api/v1/catalog/assets/${id}/detail`)),

  getDataQualityRuleOptions: async (): Promise<DataQualityRuleOptionsResponse> =>
    unwrap(api.get<ApiEnvelope<DataQualityRuleOptionsResponse>>('/api/v1/data-quality/rule-options')),

  getDataQualityRules: async (params?: {
    q?: string
    asset_id?: number
    event_id?: number
    rule_type?: string
    severity?: string
    status?: string
    limit?: number
  }): Promise<DataQualityRule[]> => unwrap(api.get<ApiEnvelope<DataQualityRule[]>>('/api/v1/data-quality/rules', { params })),

  createDataQualityRule: async (payload: {
    name: string
    asset_id?: number | null
    event_id?: number | null
    rule_type: string
    target_field?: string | null
    operator?: string | null
    threshold?: Record<string, unknown>
    alert_channels?: string[]
    severity?: string
    status?: string
    description?: string | null
  }): Promise<DataQualityRule> =>
    unwrap(api.post<ApiEnvelope<DataQualityRule>>('/api/v1/data-quality/rules', payload)),

  updateDataQualityRule: async (
    id: number,
    payload: {
      name?: string
      asset_id?: number | null
      event_id?: number | null
      rule_type?: string
      target_field?: string | null
      operator?: string | null
      threshold?: Record<string, unknown>
      alert_channels?: string[]
      severity?: string
      status?: string
      description?: string | null
    },
  ): Promise<DataQualityRule> =>
    unwrap(api.patch<ApiEnvelope<DataQualityRule>>(`/api/v1/data-quality/rules/${id}`, payload)),

  getDataQualityRuleDetail: async (id: number): Promise<DataQualityRuleDetailResponse> =>
    unwrap(api.get<ApiEnvelope<DataQualityRuleDetailResponse>>(`/api/v1/data-quality/rules/${id}/detail`)),

  runDataQualityRule: async (
    id: number,
    payload?: {
      checked_count?: number
      failed_count?: number
      simulated_failure_rate?: number
      trigger_source?: string
      notes?: string
    },
  ): Promise<DataQualityRuleRunResponse> =>
    unwrap(api.post<ApiEnvelope<DataQualityRuleRunResponse>>(`/api/v1/data-quality/rules/${id}/run`, payload ?? {})),

  getSchedulerOptions: async (): Promise<SchedulerOptionsResponse> =>
    unwrap(api.get<ApiEnvelope<SchedulerOptionsResponse>>('/api/v1/scheduler/options')),

  getSchedulerDags: async (params?: {
    q?: string
    status?: string
    trigger_mode?: string
    limit?: number
  }): Promise<SchedulerDagSummary[]> =>
    unwrap(api.get<ApiEnvelope<SchedulerDagSummary[]>>('/api/v1/scheduler/dags', { params })),

  createSchedulerDag: async (payload: {
    name: string
    description?: string | null
    status?: string
    trigger_mode?: string
    cron_expr?: string | null
    timezone?: string
    dependency_mode?: string
    retry_policy?: Record<string, unknown>
    schedule_config?: Record<string, unknown>
    nodes: Array<{
      node_key: string
      name: string
      task_type: string
      input_assets?: string[]
      output_assets?: string[]
      logic_description?: string | null
      config?: Record<string, unknown>
      position?: Record<string, unknown>
    }>
    edges?: Array<{
      from_node_key: string
      to_node_key: string
      condition?: Record<string, unknown>
    }>
  }): Promise<SchedulerDagSummary> =>
    unwrap(api.post<ApiEnvelope<SchedulerDagSummary>>('/api/v1/scheduler/dags', payload)),

  updateSchedulerDag: async (
    id: number,
    payload: {
      name?: string
      description?: string | null
      status?: string
      trigger_mode?: string
      cron_expr?: string | null
      timezone?: string
      dependency_mode?: string
      retry_policy?: Record<string, unknown>
      schedule_config?: Record<string, unknown>
      nodes?: Array<{
        node_key: string
        name: string
        task_type: string
        input_assets?: string[]
        output_assets?: string[]
        logic_description?: string | null
        config?: Record<string, unknown>
        position?: Record<string, unknown>
      }>
      edges?: Array<{
        from_node_key: string
        to_node_key: string
        condition?: Record<string, unknown>
      }>
    },
  ): Promise<SchedulerDagSummary> =>
    unwrap(api.patch<ApiEnvelope<SchedulerDagSummary>>(`/api/v1/scheduler/dags/${id}`, payload)),

  getSchedulerDagDetail: async (id: number): Promise<SchedulerDagDetailResponse> =>
    unwrap(api.get<ApiEnvelope<SchedulerDagDetailResponse>>(`/api/v1/scheduler/dags/${id}/detail`)),

  getSchedulerDagRuns: async (id: number, params?: { limit?: number }): Promise<SchedulerRun[]> =>
    unwrap(api.get<ApiEnvelope<SchedulerRun[]>>(`/api/v1/scheduler/dags/${id}/runs`, { params })),

  runSchedulerDag: async (
    id: number,
    payload?: {
      trigger_source?: string
      run_context?: Record<string, unknown>
      forced_node_results?: Record<string, string>
      notes?: string
    },
  ): Promise<SchedulerDagRunResponse> =>
    unwrap(api.post<ApiEnvelope<SchedulerDagRunResponse>>(`/api/v1/scheduler/dags/${id}/run`, payload ?? {})),

  getSchedulerRunDetail: async (id: number): Promise<SchedulerRunDetailResponse> =>
    unwrap(api.get<ApiEnvelope<SchedulerRunDetailResponse>>(`/api/v1/scheduler/runs/${id}/detail`)),

  applySchedulerRunAction: async (
    runId: number,
    payload: {
      action: 'RETRY' | 'SKIP' | 'MARK_SUCCESS' | string
      node_run_id?: number
      reason?: string
    },
  ): Promise<SchedulerDagRunResponse> =>
    unwrap(api.post<ApiEnvelope<SchedulerDagRunResponse>>(`/api/v1/scheduler/runs/${runId}/actions`, payload)),

  tickSchedulerEngine: async (payload?: { run_immediately?: boolean; limit?: number }): Promise<SchedulerEngineTickResponse> =>
    unwrap(api.post<ApiEnvelope<SchedulerEngineTickResponse>>('/api/v1/scheduler/engine/tick', payload ?? {})),

  getEventGovernancePayload: async (
    id: number,
  ): Promise<{ event_id: number; name: string; description: string; properties: Record<string, unknown> }> =>
    unwrap(api.post<ApiEnvelope<{ event_id: number; name: string; description: string; properties: Record<string, unknown> }>>(`/api/v1/events/${id}/submit-governance`)),

  getOverview: async (): Promise<OverviewResponse> =>
    unwrap(api.get<ApiEnvelope<OverviewResponse>>('/api/v1/overview')),

  getP0Overview: async (): Promise<P0OverviewResponse> =>
    unwrap(api.get<ApiEnvelope<P0OverviewResponse>>('/api/v1/p0/overview')),

  getP0SourceProfiles: async (
    query: P0SourceProfileQuery = {},
  ): Promise<P0EntityListResponse<P0SourceProfile>> =>
    unwrap(
      api.get<ApiEnvelope<P0EntityListResponse<P0SourceProfile>>>('/api/v1/p0/source-profiles', {
        params: { limit: query.limit ?? 12, offset: query.offset ?? 0, heat: query.heat, q: query.q },
      }),
    ),

  getP0SourceProfileDetail: async (id: number): Promise<P0SourceProfile & { profile_payload?: Record<string, unknown> }> =>
    unwrap(api.get<ApiEnvelope<P0SourceProfile & { profile_payload?: Record<string, unknown> }>>(`/api/v1/p0/source-profiles/${id}`)),

  getP0InferenceCandidates: async (
    query: P0InferenceCandidateQuery = {},
  ): Promise<P0EntityListResponse<P0InferenceCandidate>> =>
    unwrap(
      api.get<ApiEnvelope<P0EntityListResponse<P0InferenceCandidate>>>(
        '/api/v1/p0/inference-candidates',
        {
          params: {
            limit: query.limit ?? 12,
            offset: query.offset ?? 0,
            candidate_type: query.candidate_type,
            status: query.status,
            q: query.q,
          },
        },
      ),
    ),

  getP0InferenceCandidateDetail: async (id: number): Promise<P0InferenceCandidate> =>
    unwrap(api.get<ApiEnvelope<P0InferenceCandidate>>(`/api/v1/p0/inference-candidates/${id}`)),

  getP0GovernanceRecords: async (
    query: P0GovernanceRecordQuery = {},
  ): Promise<P0EntityListResponse<P0GovernanceRecord>> =>
    unwrap(
      api.get<ApiEnvelope<P0EntityListResponse<P0GovernanceRecord>>>(
        '/api/v1/p0/governance-records',
        {
          params: {
            limit: query.limit ?? 16,
            offset: query.offset ?? 0,
            queue_status: query.queue_status,
            decision_status: query.decision_status,
            q: query.q,
          },
        },
      ),
    ),

  getP0GovernanceRecordDetail: async (id: number): Promise<P0GovernanceRecord> =>
    unwrap(api.get<ApiEnvelope<P0GovernanceRecord>>(`/api/v1/p0/governance-records/${id}`)),

  getP0ContractArtifacts: async (
    query: P0ContractArtifactQuery = {},
  ): Promise<P0EntityListResponse<P0ContractArtifact>> =>
    unwrap(
      api.get<ApiEnvelope<P0EntityListResponse<P0ContractArtifact>>>(
        '/api/v1/p0/contract-artifacts',
        {
          params: {
            limit: query.limit ?? 12,
            offset: query.offset ?? 0,
            serving_status: query.serving_status,
            q: query.q,
          },
        },
      ),
    ),

  getP0ContractArtifactDetail: async (id: number): Promise<P0ContractArtifact> =>
    unwrap(api.get<ApiEnvelope<P0ContractArtifact>>(`/api/v1/p0/contract-artifacts/${id}`)),

  getFabricSourceProfiles: async (params?: {
    q?: string
    source_type?: string
    heat?: string
    limit?: number
    offset?: number
  }): Promise<FabricListResponse<FabricSourceProfile>> =>
    unwrap(api.get<ApiEnvelope<FabricListResponse<FabricSourceProfile>>>('/api/v1/fabric/source-profiles', { params })),

  getFabricUpdateSemantics: async (params?: {
    q?: string
    mode?: string
    limit?: number
    offset?: number
  }): Promise<FabricListResponse<FabricUpdateSemantic>> =>
    unwrap(api.get<ApiEnvelope<FabricListResponse<FabricUpdateSemantic>>>('/api/v1/fabric/update-semantics', { params })),

  getFabricSemanticDomains: async (): Promise<FabricSemanticDomainResponse> =>
    unwrap(api.get<ApiEnvelope<FabricSemanticDomainResponse>>('/api/v1/fabric/semantic-domains')),

  planFabricQuery: async (payload: {
    question: string
    latency_target_ms?: number
  }): Promise<FabricQueryPlan> =>
    unwrap(api.post<ApiEnvelope<FabricQueryPlan>>('/api/v1/fabric/planner/plan', payload)),

  submitFabricQuery: async (payload: {
    question: string
    latency_target_ms?: number
  }): Promise<FabricQuerySubmission> =>
    unwrap(api.post<ApiEnvelope<FabricQuerySubmission>>('/api/v1/fabric/planner/submit', payload)),

  getFabricQueryRuns: async (params?: {
    q?: string
    status?: string
    intent_type?: string
    selected_path?: string
    limit?: number
    offset?: number
  }): Promise<FabricListResponse<FabricQueryRunListItem>> =>
    unwrap(api.get<ApiEnvelope<FabricListResponse<FabricQueryRunListItem>>>('/api/v1/fabric/planner/runs', { params })),

  getFabricQueryRunDetail: async (runId: number): Promise<FabricQueryRunDetail | null> =>
    unwrap(api.get<ApiEnvelope<FabricQueryRunDetail | null>>(`/api/v1/fabric/planner/runs/${runId}`)),

  getFabricTrace: async (traceId: string): Promise<FabricTraceResponse | null> =>
    unwrap(api.get<ApiEnvelope<FabricTraceResponse | null>>(`/api/v1/fabric/traces/${traceId}`)),

  getFabricMaterializations: async (params?: {
    q?: string
    status?: string
    limit?: number
    offset?: number
  }): Promise<FabricListResponse<FabricMaterialization>> =>
    unwrap(api.get<ApiEnvelope<FabricListResponse<FabricMaterialization>>>('/api/v1/fabric/materializations', { params })),

  getFabricMaterializationArtifacts: async (params?: {
    q?: string
    status?: string
    heat?: string
    limit?: number
    offset?: number
  }): Promise<FabricListResponse<FabricMaterializationArtifact>> =>
    unwrap(api.get<ApiEnvelope<FabricListResponse<FabricMaterializationArtifact>>>('/api/v1/fabric/materialization-artifacts', { params })),

  getFabricTelemetryOverview: async (): Promise<FabricTelemetryOverview> =>
    unwrap(api.get<ApiEnvelope<FabricTelemetryOverview>>('/api/v1/fabric/telemetry/overview')),

  listSourceOnboardingSources: async (params?: {
    q?: string
    source_type?: string
    status?: string
    heat?: string
    page?: number
    page_size?: number
  }): Promise<SourceOnboardingListResponse> =>
    unwrap(api.get<ApiEnvelope<SourceOnboardingListResponse>>('/api/v1/source-onboarding/sources', { params })),

  createSourceOnboardingSource: async (payload: {
    source_name: string
    source_type: SourceOnboardingType | string
    config: SourceOnboardingConfig
  }): Promise<SourceOnboardingSource> =>
    unwrap(api.post<ApiEnvelope<SourceOnboardingSource>>('/api/v1/source-onboarding/sources', payload)),

  getSourceOnboardingSource: async (id: number): Promise<SourceOnboardingSource> =>
    unwrap(api.get<ApiEnvelope<SourceOnboardingSource>>(`/api/v1/source-onboarding/sources/${id}`)),

  updateSourceOnboardingSource: async (
    id: number,
    payload: {
      source_name?: string
      config?: SourceOnboardingConfig
    },
  ): Promise<SourceOnboardingSource> =>
    unwrap(api.put<ApiEnvelope<SourceOnboardingSource>>(`/api/v1/source-onboarding/sources/${id}`, payload)),

  deleteSourceOnboardingSource: async (id: number): Promise<SourceOnboardingDeleteResult> =>
    unwrap(api.delete<ApiEnvelope<SourceOnboardingDeleteResult>>(`/api/v1/source-onboarding/sources/${id}`)),

  testSourceOnboardingConnection: async (id: number): Promise<SourceOnboardingConnectionResult> =>
    unwrap(api.post<ApiEnvelope<SourceOnboardingConnectionResult>>(`/api/v1/source-onboarding/sources/${id}/test`)),

  scanSourceOnboardingSource: async (id: number): Promise<SourceOnboardingScanResult> =>
    unwrap(api.post<ApiEnvelope<SourceOnboardingScanResult>>(`/api/v1/source-onboarding/sources/${id}/scan`)),

  listSourceIntakeConnectors: async (params?: {
    q?: string
    category?: string
    status?: string
  }): Promise<{ items: ConnectorDefinition[]; categories: string[] }> =>
    unwrap(api.get<ApiEnvelope<{ items: ConnectorDefinition[]; categories: string[] }>>('/api/v1/source-intake/connectors', { params })),

  listSourceInstances: async (params?: {
    q?: string
    connector_key?: string
    status?: string
    heat?: string
    page?: number
    page_size?: number
  }): Promise<SourceIntakePagedResponse<SourceInstance>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceInstance>>>('/api/v1/source-intake/instances', { params })),

  createSourceInstance: async (payload: {
    instance_name: string
    connector_key: string
    config: Record<string, unknown>
  }): Promise<SourceInstance> =>
    unwrap(api.post<ApiEnvelope<SourceInstance>>('/api/v1/source-intake/instances', payload)),

  getSourceInstance: async (id: number): Promise<SourceInstance> =>
    unwrap(api.get<ApiEnvelope<SourceInstance>>(`/api/v1/source-intake/instances/${id}`)),

  updateSourceInstance: async (
    id: number,
    payload: {
      instance_name?: string
      config?: Record<string, unknown>
      memory_scope_default?: string
      watch_enabled?: boolean
      watch_interval_seconds?: number
    },
  ): Promise<SourceInstance> =>
    unwrap(api.patch<ApiEnvelope<SourceInstance>>(`/api/v1/source-intake/instances/${id}`, payload)),

  deleteSourceInstance: async (id: number): Promise<{ id: number; deleted: boolean; instance_name: string }> =>
    unwrap(api.delete<ApiEnvelope<{ id: number; deleted: boolean; instance_name: string }>>(`/api/v1/source-intake/instances/${id}`)),

  testSourceInstance: async (id: number): Promise<{ status: string; message: string; instance: SourceInstance }> =>
    unwrap(api.post<ApiEnvelope<{ status: string; message: string; instance: SourceInstance }>>(`/api/v1/source-intake/instances/${id}/test`)),

  discoverSourceInstance: async (id: number): Promise<{
    instance: SourceInstance
    discovery: Record<string, unknown>
    changes: SourceChangeEvent[]
    candidates: SourceCandidate[]
    brief: SourceBrief
  }> =>
    unwrap(api.post<ApiEnvelope<{
      instance: SourceInstance
      discovery: Record<string, unknown>
      changes: SourceChangeEvent[]
      candidates: SourceCandidate[]
      brief: SourceBrief
    }>>(`/api/v1/source-intake/instances/${id}/discover`)),

  runSourceWatch: async (id: number): Promise<{
    instance: SourceInstance
    discovery: Record<string, unknown>
    changes: SourceChangeEvent[]
    candidates: SourceCandidate[]
    brief: SourceBrief
  }> =>
    unwrap(api.post<ApiEnvelope<{
      instance: SourceInstance
      discovery: Record<string, unknown>
      changes: SourceChangeEvent[]
      candidates: SourceCandidate[]
      brief: SourceBrief
    }>>(`/api/v1/source-intake/instances/${id}/watch/run`)),

  listSourceAssets: async (params?: {
    q?: string
    instance_id?: number
    asset_type?: string
    heat?: string
    status?: string
    updated_since?: string
    page?: number
    page_size?: number
  }): Promise<SourceIntakePagedResponse<SourceAsset>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceAsset>>>('/api/v1/source-intake/assets', { params })),

  listInstanceAssets: async (
    instanceId: number,
    params?: {
      q?: string
      asset_type?: string
      heat?: string
      status?: string
      updated_since?: string
      page?: number
      page_size?: number
    },
  ): Promise<SourceIntakePagedResponse<SourceAsset>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceAsset>>>(`/api/v1/source-intake/instances/${instanceId}/assets`, { params })),

  listSourceAssetFields: async (
    assetId: number,
    params?: {
      q?: string
      candidate_type?: string
      status?: string
      page?: number
      page_size?: number
    },
  ): Promise<SourceIntakePagedResponse<SourceField>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceField>>>(`/api/v1/source-intake/assets/${assetId}/fields`, { params })),

  getSourceField: async (fieldId: number): Promise<SourceField> =>
    unwrap(api.get<ApiEnvelope<SourceField>>(`/api/v1/source-intake/fields/${fieldId}`)),

  getSourceFieldProfiles: async (fieldId: number): Promise<SourceFieldProfile[]> =>
    unwrap(api.get<ApiEnvelope<SourceFieldProfile[]>>(`/api/v1/source-intake/fields/${fieldId}/profiles`)),

  getSourceFieldCandidates: async (fieldId: number): Promise<SemanticCandidate[]> =>
    unwrap(api.get<ApiEnvelope<SemanticCandidate[]>>(`/api/v1/source-intake/fields/${fieldId}/candidates`)),

  listSourceChangeEvents: async (params?: {
    q?: string
    status?: string
    severity?: string
    page?: number
    page_size?: number
  }): Promise<SourceIntakePagedResponse<SourceChangeEvent>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceChangeEvent>>>('/api/v1/source-intake/change-events', { params })),

  listSourceCandidates: async (params?: {
    q?: string
    status?: string
    candidate_type?: string
    memory_scope_target?: string
    page?: number
    page_size?: number
  }): Promise<SourceIntakePagedResponse<SourceCandidate>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceCandidate>>>('/api/v1/source-intake/candidates', { params })),

  promoteSourceCandidate: async (id: number): Promise<SourceCandidate> =>
    unwrap(api.post<ApiEnvelope<SourceCandidate>>(`/api/v1/source-intake/candidates/${id}/promote`)),

  shareSourceCandidate: async (id: number): Promise<SourceCandidate> =>
    unwrap(api.post<ApiEnvelope<SourceCandidate>>(`/api/v1/source-intake/candidates/${id}/share`)),

  dismissSourceCandidate: async (id: number): Promise<SourceCandidate> =>
    unwrap(api.post<ApiEnvelope<SourceCandidate>>(`/api/v1/source-intake/candidates/${id}/dismiss`)),

  listSourceBriefs: async (params?: {
    instance_id?: number
    page?: number
    page_size?: number
  }): Promise<SourceIntakePagedResponse<SourceBrief>> =>
    unwrap(api.get<ApiEnvelope<SourceIntakePagedResponse<SourceBrief>>>('/api/v1/source-intake/briefs', { params })),

  getSourceTelemetryOverview: async (params?: { instance_id?: number }): Promise<SourceTelemetryOverview> =>
    unwrap(api.get<ApiEnvelope<SourceTelemetryOverview>>('/api/v1/source-intake/telemetry/overview', { params })),

  getSourceTelemetrySeries: async (params?: { window?: string; instance_id?: number }): Promise<SourceTelemetrySeriesResponse> =>
    unwrap(api.get<ApiEnvelope<SourceTelemetrySeriesResponse>>('/api/v1/source-intake/telemetry/source-series', { params })),

  getNodeTelemetrySeries: async (params?: { window?: string; instance_id?: number }): Promise<SourceTelemetrySeriesResponse> =>
    unwrap(api.get<ApiEnvelope<SourceTelemetrySeriesResponse>>('/api/v1/source-intake/telemetry/node-series', { params })),

  getInstanceTelemetry: async (instanceId: number, params?: { window?: string }): Promise<SourceInstanceTelemetry> =>
    unwrap(api.get<ApiEnvelope<SourceInstanceTelemetry>>(`/api/v1/source-intake/instances/${instanceId}/telemetry`, { params })),

  getSettingsOverview: async (): Promise<SettingsOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<SettingsOverviewResponse>>('/api/v1/settings')),

  getSettingsGeneral: async (): Promise<SettingsGeneral> =>
    unwrap(api.get<ApiEnvelope<SettingsGeneral>>('/api/v1/settings/general')),

  updateSettingsGeneral: async (payload: {
    name?: string
    description?: string | null
    tags?: string[]
    default_domain?: string | null
  }): Promise<SettingsGeneral> =>
    unwrap(api.patch<ApiEnvelope<SettingsGeneral>>('/api/v1/settings/general', payload)),

  getSettingsMembers: async (): Promise<SettingsMembersResponse> =>
    unwrap(api.get<ApiEnvelope<SettingsMembersResponse>>('/api/v1/settings/members')),

  inviteSettingsMember: async (payload: {
    email: string
    name?: string
    role: string
  }): Promise<{
    mode: string
    member?: SettingsMember | null
    pending_invitation?: SettingsPendingInvitation | null
  }> => unwrap(api.post<ApiEnvelope<{
    mode: string
    member?: SettingsMember | null
    pending_invitation?: SettingsPendingInvitation | null
  }>>('/api/v1/settings/members/invite', payload)),

  updateSettingsMemberRole: async (userId: number, payload: {
    role: string
  }): Promise<SettingsMember> =>
    unwrap(api.patch<ApiEnvelope<SettingsMember>>(`/api/v1/settings/members/${userId}/role`, payload)),

  removeSettingsMember: async (userId: number): Promise<{ user_id: number }> =>
    unwrap(api.delete<ApiEnvelope<{ user_id: number }>>(`/api/v1/settings/members/${userId}`)),

  getSettingsIntegrations: async (): Promise<SettingsIntegrationItem[]> =>
    unwrap(api.get<ApiEnvelope<SettingsIntegrationItem[]>>('/api/v1/settings/integrations')),

  testSettingsIntegration: async (payload: {
    integration_type: string
    config: Record<string, unknown>
  }): Promise<SettingsIntegrationTestResult> =>
    unwrap(api.post<ApiEnvelope<SettingsIntegrationTestResult>>('/api/v1/settings/integrations/test', payload)),

  saveSettingsIntegration: async (integrationType: string, payload: {
    enabled?: boolean
    config?: Record<string, unknown>
  }): Promise<SettingsIntegrationItem> =>
    unwrap(api.put<ApiEnvelope<SettingsIntegrationItem>>(`/api/v1/settings/integrations/${integrationType}`, payload)),

  getSettingsSecurity: async (): Promise<SettingsSecurity> =>
    unwrap(api.get<ApiEnvelope<SettingsSecurity>>('/api/v1/settings/security')),

  updateSettingsSecurity: async (payload: {
    sso_enabled?: boolean
    mfa_required?: boolean
    password_min_length?: number
    password_require_upper?: boolean
    password_require_lower?: boolean
    password_require_number?: boolean
    password_require_symbol?: boolean
    audit_log_retention_days?: number
    audit_export_requires_approval?: boolean
    max_exports_per_day?: number
  }): Promise<SettingsSecurity> =>
    unwrap(api.patch<ApiEnvelope<SettingsSecurity>>('/api/v1/settings/security', payload)),

  getExploreSources: async (): Promise<ExploreSourceSummary[]> =>
    unwrap(api.get<ApiEnvelope<ExploreSourceSummary[]>>('/api/v1/explore/sources')),

  getExploreCatalogTree: async (params?: { source_system?: string }): Promise<ExploreCatalogSourceNode[]> =>
    unwrap(api.get<ApiEnvelope<ExploreCatalogSourceNode[]>>('/api/v1/explore/catalog/tree', { params })),

  getExploreAssetProfile: async (assetId: number): Promise<ExploreAssetProfile> =>
    unwrap(api.get<ApiEnvelope<ExploreAssetProfile>>(`/api/v1/explore/assets/${assetId}/profile`)),

  runExploreQuery: async (payload: {
    sql: string
    page?: number
    page_size?: number
  }): Promise<ExploreQueryResponse> =>
    unwrap(api.post<ApiEnvelope<ExploreQueryResponse>>('/api/v1/explore/query', payload)),

  exportExploreQuery: async (payload: { sql: string; format: 'csv' | 'json' }): Promise<ExploreExportResponse> =>
    unwrap(api.post<ApiEnvelope<ExploreExportResponse>>('/api/v1/explore/query/export', payload)),

  getExplorePrefill: async (params: { source_type: string; source_id: string | number }): Promise<ExplorePrefillResponse> =>
    unwrap(api.get<ApiEnvelope<ExplorePrefillResponse>>('/api/v1/explore/prefill', { params })),

  getInfrastructureOverview: async (params?: {
    environment?: string
    cluster?: string
  }): Promise<InfrastructureOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<InfrastructureOverviewResponse>>('/api/v1/infrastructure/overview', { params })),

  getMonitoringOverview: async (params?: {
    modules?: string
    window_minutes?: number
    bucket_count?: number
  }): Promise<MonitoringOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<MonitoringOverviewResponse>>('/api/v1/monitoring/overview', { params })),

  getMonitoringAlerts: async (params?: {
    q?: string
    severity?: string
    status?: string
    source_module?: string
    date_from?: string
    date_to?: string
    limit?: number
    offset?: number
  }): Promise<MonitoringAlertListResponse> =>
    unwrap(api.get<ApiEnvelope<MonitoringAlertListResponse>>('/api/v1/monitoring/alerts', { params })),

  getMonitoringAlertDetail: async (id: number): Promise<MonitoringAlertDetailResponse> =>
    unwrap(api.get<ApiEnvelope<MonitoringAlertDetailResponse>>(`/api/v1/monitoring/alerts/${id}`)),

  operateMonitoringAlert: async (
    id: number,
    payload: {
      action: 'CLAIM' | 'RESOLVE' | 'NOTE' | string
      note?: string
      assignee?: string
    },
  ): Promise<MonitoringAlertActionResponse> =>
    unwrap(api.post<ApiEnvelope<MonitoringAlertActionResponse>>(`/api/v1/monitoring/alerts/${id}/actions`, payload)),

  getCollaborationOverview: async (): Promise<CollaborationOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<CollaborationOverviewResponse>>('/api/v1/collaboration/overview')),

  getCollaborationWorkflows: async (params?: {
    q?: string
    status?: string
    workflow_type?: string
    source_type?: string
    initiated_by_me?: boolean
    my_todos_only?: boolean
    limit?: number
    offset?: number
  }): Promise<CollaborationWorkflowListResponse> =>
    unwrap(api.get<ApiEnvelope<CollaborationWorkflowListResponse>>('/api/v1/collaboration/workflows', { params })),

  createCollaborationWorkflow: async (payload: {
    workflow_type: string
    source_type: string
    source_id: string
    title: string
    description?: string | null
    priority?: string
    assignee_user_id?: number | null
    assignee_role?: string | null
    due_in_hours?: number | null
    context_payload?: Record<string, unknown>
    initial_task_title?: string | null
    initial_task_description?: string | null
  }): Promise<CollaborationWorkflowDetailResponse> =>
    unwrap(api.post<ApiEnvelope<CollaborationWorkflowDetailResponse>>('/api/v1/collaboration/workflows', payload)),

  getCollaborationWorkflowDetail: async (id: number): Promise<CollaborationWorkflowDetailResponse> =>
    unwrap(api.get<ApiEnvelope<CollaborationWorkflowDetailResponse>>(`/api/v1/collaboration/workflows/${id}`)),

  addCollaborationComment: async (
    workflowId: number,
    payload: { content: string },
  ): Promise<CollaborationCommentItem> =>
    unwrap(api.post<ApiEnvelope<CollaborationCommentItem>>(`/api/v1/collaboration/workflows/${workflowId}/comments`, payload)),

  operateCollaborationWorkflow: async (
    workflowId: number,
    payload: {
      action: 'APPROVE' | 'REJECT' | 'REQUEST_REVISION' | 'START' | 'COMPLETE' | 'ASSIGN' | string
      note?: string
      assignee_user_id?: number
      assignee_role?: string
    },
  ): Promise<CollaborationWorkflowDetailResponse> =>
    unwrap(api.post<ApiEnvelope<CollaborationWorkflowDetailResponse>>(`/api/v1/collaboration/workflows/${workflowId}/actions`, payload)),

  getKnowledgeOverview: async (): Promise<KnowledgeOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<KnowledgeOverviewResponse>>('/api/v1/knowledge/overview')),

  getKnowledgeTemplates: async (): Promise<KnowledgeTemplateItem[]> =>
    unwrap(api.get<ApiEnvelope<KnowledgeTemplateItem[]>>('/api/v1/knowledge/templates')),

  getKnowledgeDocuments: async (params?: {
    q?: string
    module?: string
    knowledge_level?: string
    doc_type?: string
    status?: string
    tag?: string
    updated_by_me?: boolean
    related_source_type?: string
    related_source_id?: string
    include_shared?: boolean
    shared_only?: boolean
    limit?: number
    offset?: number
  }): Promise<KnowledgeDocumentListResponse> =>
    unwrap(api.get<ApiEnvelope<KnowledgeDocumentListResponse>>('/api/v1/knowledge/documents', { params })),

  getKnowledgeRelatedDocuments: async (params: {
    source_type: string
    source_id: string
    include_archived?: boolean
    limit?: number
  }): Promise<{ source_type: string; source_id: string; items: KnowledgeDocumentItem[]; total: number }> =>
    unwrap(api.get<ApiEnvelope<{ source_type: string; source_id: string; items: KnowledgeDocumentItem[]; total: number }>>('/api/v1/knowledge/documents/related', { params })),

  createKnowledgeDocument: async (payload: {
    doc_type: string
    module: string
    knowledge_level?: string
    title: string
    summary?: string | null
    content?: string | null
    format?: string
    status?: string
    tags?: string[]
    related_objects?: Array<{
      source_type: string
      source_id: string
      label?: string
      module?: string
    }>
    meta_payload?: Record<string, unknown>
    object_refs?: Array<Record<string, unknown>>
    fact_refs?: Array<Record<string, unknown>>
    template_key?: string
    change_note?: string
  }): Promise<KnowledgeDocumentDetailResponse> =>
    unwrap(api.post<ApiEnvelope<KnowledgeDocumentDetailResponse>>('/api/v1/knowledge/documents', payload)),

  getKnowledgeDocumentDetail: async (id: number): Promise<KnowledgeDocumentDetailResponse> =>
    unwrap(api.get<ApiEnvelope<KnowledgeDocumentDetailResponse>>(`/api/v1/knowledge/documents/${id}`)),

  updateKnowledgeDocument: async (
    id: number,
    payload: {
      doc_type?: string
      module?: string
      knowledge_level?: string
      title?: string
      summary?: string | null
      content?: string
      format?: string
      tags?: string[]
      related_objects?: Array<{
        source_type: string
        source_id: string
        label?: string
        module?: string
      }>
      meta_payload?: Record<string, unknown>
      object_refs?: Array<Record<string, unknown>>
      fact_refs?: Array<Record<string, unknown>>
      change_note?: string
    },
  ): Promise<KnowledgeDocumentDetailResponse> =>
    unwrap(api.patch<ApiEnvelope<KnowledgeDocumentDetailResponse>>(`/api/v1/knowledge/documents/${id}`, payload)),

  addKnowledgeDocumentComment: async (
    id: number,
    payload: { content: string },
  ): Promise<KnowledgeDocumentCommentItem> =>
    unwrap(api.post<ApiEnvelope<KnowledgeDocumentCommentItem>>(`/api/v1/knowledge/documents/${id}/comments`, payload)),

  operateKnowledgeDocument: async (
    id: number,
    payload: { action: 'PUBLISH' | 'ARCHIVE' | 'UNARCHIVE' | string; change_note?: string },
  ): Promise<KnowledgeDocumentDetailResponse> =>
    unwrap(api.post<ApiEnvelope<KnowledgeDocumentDetailResponse>>(`/api/v1/knowledge/documents/${id}/actions`, payload)),

  restoreKnowledgeDocumentVersion: async (
    id: number,
    versionId: number,
    payload?: { change_note?: string },
  ): Promise<KnowledgeDocumentDetailResponse> =>
    unwrap(api.post<ApiEnvelope<KnowledgeDocumentDetailResponse>>(`/api/v1/knowledge/documents/${id}/versions/${versionId}/restore`, payload ?? {})),

  assistantChat: async (payload: {
    messages: AssistantChatMessage[]
    include_knowledge?: boolean
    include_sources?: boolean
    runtime_config?: AssistantRuntimeConfigPayload
  }): Promise<AssistantChatResponse> =>
    unwrap(api.post<ApiEnvelope<AssistantChatResponse>>('/api/v1/assistant/chat', payload)),

  getCostUsageOverview: async (params?: {
    scope?: 'PROJECT' | 'TENANT' | string
    project_id?: number
    module?: string
    resource_type?: string
    date_from?: string
    date_to?: string
    window_days?: number
    granularity?: 'DAY' | 'HOUR' | string
    top_n?: number
  }): Promise<CostUsageOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<CostUsageOverviewResponse>>('/api/v1/cost/overview', { params })),

  getCostUsageResources: async (params?: {
    scope?: 'PROJECT' | 'TENANT' | string
    project_id?: number
    module?: string
    resource_type?: string
    q?: string
    date_from?: string
    date_to?: string
    window_days?: number
    sort_by?: 'COST' | 'USAGE' | 'NAME' | 'UPDATED' | string
    limit?: number
    offset?: number
  }): Promise<CostUsageResourceListResponse> =>
    unwrap(api.get<ApiEnvelope<CostUsageResourceListResponse>>('/api/v1/cost/resources', { params })),

  getCostUsageResourceDetail: async (
    sourceType: string,
    sourceId: string,
    params?: {
      scope?: 'PROJECT' | 'TENANT' | string
      project_id?: number
      date_from?: string
      date_to?: string
      window_days?: number
      granularity?: 'DAY' | 'HOUR' | string
    },
  ): Promise<CostUsageResourceDetailResponse> =>
    unwrap(
      api.get<ApiEnvelope<CostUsageResourceDetailResponse>>(
        `/api/v1/cost/resources/${encodeURIComponent(sourceType)}/${encodeURIComponent(sourceId)}`,
        { params },
      ),
    ),

  getSandboxOverview: async (): Promise<SandboxOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<SandboxOverviewResponse>>('/api/v1/sandbox/overview')),

  getSandboxOptions: async (params?: {
    experiment_type?: SandboxExperimentType
  }): Promise<SandboxOptionsResponse> =>
    unwrap(api.get<ApiEnvelope<SandboxOptionsResponse>>('/api/v1/sandbox/options', { params })),

  getSandboxExperiments: async (params?: {
    q?: string
    status?: SandboxExperimentStatus | string
    experiment_type?: SandboxExperimentType | string
    source_type?: string
    limit?: number
    offset?: number
  }): Promise<SandboxExperimentListResponse> =>
    unwrap(api.get<ApiEnvelope<SandboxExperimentListResponse>>('/api/v1/sandbox/experiments', { params })),

  createSandboxExperiment: async (payload: {
    experiment_type: SandboxExperimentType
    title: string
    description?: string | null
    source_type: string
    source_id: string
    sandbox_source_type?: string | null
    sandbox_source_id?: string | null
    config_payload?: Record<string, unknown>
  }): Promise<SandboxExperimentItem> =>
    unwrap(api.post<ApiEnvelope<SandboxExperimentItem>>('/api/v1/sandbox/experiments', payload)),

  getSandboxExperimentDetail: async (id: number): Promise<SandboxExperimentDetailResponse> =>
    unwrap(api.get<ApiEnvelope<SandboxExperimentDetailResponse>>(`/api/v1/sandbox/experiments/${id}`)),

  runSandboxExperiment: async (
    id: number,
    payload?: {
      sample_size?: number
      traffic_ratio?: number
      candidate_payloads?: Array<Record<string, unknown>>
      run_context?: Record<string, unknown>
      notes?: string
    },
  ): Promise<SandboxRunResponse> =>
    unwrap(api.post<ApiEnvelope<SandboxRunResponse>>(`/api/v1/sandbox/experiments/${id}/runs`, payload ?? {})),

  promoteSandboxExperiment: async (
    id: number,
    payload?: { candidate_key?: string; note?: string },
  ): Promise<SandboxPromoteResponse> =>
    unwrap(
      api.post<ApiEnvelope<SandboxPromoteResponse>>(
        `/api/v1/sandbox/experiments/${id}/promote`,
        payload ?? {},
      ),
    ),

  getIntegrationHubOverview: async (): Promise<IntegrationHubOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<IntegrationHubOverviewResponse>>('/api/v1/integration-hub/overview')),

  getIntegrationHubIntegrations: async (params?: {
    q?: string
    integration_type?: string
    category?: string
    enabled?: boolean
    health_status?: string
    limit?: number
    offset?: number
  }): Promise<IntegrationHubListResponse> =>
    unwrap(api.get<ApiEnvelope<IntegrationHubListResponse>>('/api/v1/integration-hub/integrations', { params })),

  getIntegrationHubDetail: async (integrationType: string): Promise<IntegrationHubDetailResponse> =>
    unwrap(
      api.get<ApiEnvelope<IntegrationHubDetailResponse>>(
        `/api/v1/integration-hub/integrations/${encodeURIComponent(integrationType)}`,
      ),
    ),

  testIntegrationHub: async (payload: {
    integration_type: string
    config: Record<string, unknown>
  }): Promise<IntegrationHubTestResponse> =>
    unwrap(api.post<ApiEnvelope<IntegrationHubTestResponse>>('/api/v1/integration-hub/test', payload)),

  saveIntegrationHub: async (
    integrationType: string,
    payload: {
      enabled?: boolean
      config?: Record<string, unknown>
    },
  ): Promise<IntegrationHubItem> =>
    unwrap(
      api.put<ApiEnvelope<IntegrationHubItem>>(
        `/api/v1/integration-hub/integrations/${encodeURIComponent(integrationType)}`,
        payload,
      ),
    ),

  invokeIntegrationHub: async (
    integrationType: string,
    payload: {
      caller_module: string
      action: string
      payload?: Record<string, unknown>
      simulate_failure?: boolean
      error_code?: string
      note?: string
    },
  ): Promise<IntegrationHubInvokeResponse> =>
    unwrap(
      api.post<ApiEnvelope<IntegrationHubInvokeResponse>>(
        `/api/v1/integration-hub/integrations/${encodeURIComponent(integrationType)}/invoke`,
        payload,
      ),
    ),

  getAccessOverview: async (): Promise<AccessOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<AccessOverviewResponse>>('/api/v1/access/overview')),

  getAccessUsers: async (params?: {
    q?: string
    role?: string
    status?: string
    project_id?: number
    limit?: number
    offset?: number
  }): Promise<AccessUserListResponse> =>
    unwrap(api.get<ApiEnvelope<AccessUserListResponse>>('/api/v1/access/users', { params })),

  getAccessUserDetail: async (userId: number): Promise<AccessUserDetailResponse> =>
    unwrap(api.get<ApiEnvelope<AccessUserDetailResponse>>(`/api/v1/access/users/${userId}`)),

  inviteAccessUser: async (payload: {
    email: string
    name?: string
    tenant_id?: number
    project_id?: number
    tenant_role?: string
    project_role?: string
    expires_in_hours?: number
  }): Promise<AccessInviteResponse> =>
    unwrap(api.post<ApiEnvelope<AccessInviteResponse>>('/api/v1/access/users/invite', payload)),

  updateAccessUserRoles: async (
    userId: number,
    payload: {
      tenant_role_action?: 'UPSERT' | 'REMOVE' | string
      tenant_role?: string
      project_roles?: Array<{
        project_id: number
        action?: 'UPSERT' | 'REMOVE' | string
        role?: string
      }>
    },
  ): Promise<AccessUserItem> =>
    unwrap(api.patch<ApiEnvelope<AccessUserItem>>(`/api/v1/access/users/${userId}/roles`, payload)),

  updateAccessUserStatus: async (
    userId: number,
    payload: { is_active: boolean },
  ): Promise<AccessUserStatusResponse> =>
    unwrap(api.patch<ApiEnvelope<AccessUserStatusResponse>>(`/api/v1/access/users/${userId}/status`, payload)),

  getAccessRoleTemplates: async (): Promise<AccessRoleTemplateListResponse> =>
    unwrap(api.get<ApiEnvelope<AccessRoleTemplateListResponse>>('/api/v1/access/role-templates')),

  saveAccessRoleTemplate: async (
    templateKey: string,
    payload: {
      name: string
      description?: string | null
      permission_matrix: {
        modules: Record<string, string[]>
      }
      is_active?: boolean
    },
  ): Promise<AccessRoleTemplateItem> =>
    unwrap(api.put<ApiEnvelope<AccessRoleTemplateItem>>(`/api/v1/access/role-templates/${encodeURIComponent(templateKey)}`, payload)),

  deleteAccessRoleTemplate: async (
    templateKey: string,
  ): Promise<{ template_key: string; deleted: boolean }> =>
    unwrap(api.delete<ApiEnvelope<{ template_key: string; deleted: boolean }>>(`/api/v1/access/role-templates/${encodeURIComponent(templateKey)}`)),

  evaluateAccessDecision: async (payload: {
    user_id: number
    module: string
    action: string
    project_id?: number
  }): Promise<AccessEvaluateResponse> =>
    unwrap(api.post<ApiEnvelope<AccessEvaluateResponse>>('/api/v1/access/evaluate', payload)),

  getPolicyOverview: async (): Promise<PolicyOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<PolicyOverviewResponse>>('/api/v1/policy/overview')),

  getPolicyTemplates: async (): Promise<PolicyTemplateListResponse> =>
    unwrap(api.get<ApiEnvelope<PolicyTemplateListResponse>>('/api/v1/policy/templates')),

  getPolicyRules: async (params?: {
    q?: string
    rule_type?: string
    scope_type?: string
    status?: string
    severity?: string
    project_id?: number
    limit?: number
    offset?: number
  }): Promise<PolicyRuleListResponse> =>
    unwrap(api.get<ApiEnvelope<PolicyRuleListResponse>>('/api/v1/policy/rules', { params })),

  getPolicyRuleDetail: async (ruleId: number): Promise<PolicyRuleDetailResponse> =>
    unwrap(api.get<ApiEnvelope<PolicyRuleDetailResponse>>(`/api/v1/policy/rules/${ruleId}`)),

  createPolicyRule: async (payload: {
    template_key?: string
    rule_type?: string
    name?: string
    description?: string | null
    severity?: string
    status?: string
    scope_type?: string
    scope_value?: string | null
    project_id?: number
    conditions_payload?: Record<string, unknown>
    actions_payload?: Record<string, unknown>
    content_payload?: Record<string, unknown>
    prompt_text?: string | null
    change_note?: string | null
  }): Promise<PolicyRuleItem> =>
    unwrap(api.post<ApiEnvelope<PolicyRuleItem>>('/api/v1/policy/rules', payload)),

  updatePolicyRule: async (
    ruleId: number,
    payload: {
      rule_type?: string
      name?: string
      description?: string | null
      severity?: string
      status?: string
      scope_type?: string
      scope_value?: string | null
      project_id?: number
      conditions_payload?: Record<string, unknown>
      actions_payload?: Record<string, unknown>
      content_payload?: Record<string, unknown>
      prompt_text?: string | null
      change_note?: string | null
    },
  ): Promise<PolicyRuleItem> =>
    unwrap(api.patch<ApiEnvelope<PolicyRuleItem>>(`/api/v1/policy/rules/${ruleId}`, payload)),

  operatePolicyRule: async (
    ruleId: number,
    payload: {
      action: string
      change_note?: string | null
    },
  ): Promise<PolicyRuleItem> =>
    unwrap(api.post<ApiEnvelope<PolicyRuleItem>>(`/api/v1/policy/rules/${ruleId}/actions`, payload)),

  rollbackPolicyRuleVersion: async (
    ruleId: number,
    versionId: number,
    payload?: { change_note?: string | null },
  ): Promise<PolicyRuleItem> =>
    unwrap(
      api.post<ApiEnvelope<PolicyRuleItem>>(
        `/api/v1/policy/rules/${ruleId}/versions/${versionId}/rollback`,
        payload ?? {},
      ),
    ),

  evaluatePolicy: async (payload: {
    module: string
    action: string
    context_payload?: Record<string, unknown>
    include_draft?: boolean
    limit?: number
  }): Promise<PolicyEvaluateResponse> =>
    unwrap(api.post<ApiEnvelope<PolicyEvaluateResponse>>('/api/v1/policy/evaluate', payload)),

  getReleaseOverview: async (): Promise<ReleaseOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<ReleaseOverviewResponse>>('/api/v1/release/overview')),

  getReleaseChanges: async (params?: {
    q?: string
    change_type?: string
    status?: string
    priority?: string
    source_type?: string
    requested_by?: string
    date_from?: string
    date_to?: string
    limit?: number
    offset?: number
  }): Promise<ReleaseChangeListResponse> =>
    unwrap(api.get<ApiEnvelope<ReleaseChangeListResponse>>('/api/v1/release/changes', { params })),

  getReleaseChangeDetail: async (changeId: number): Promise<ReleaseChangeDetailResponse> =>
    unwrap(api.get<ApiEnvelope<ReleaseChangeDetailResponse>>(`/api/v1/release/changes/${changeId}`)),

  createReleaseChange: async (payload: {
    change_type: string
    source_type: string
    source_id: string
    title: string
    description?: string | null
    priority?: string
    impact_scope?: Record<string, unknown>
    diff_payload?: Record<string, unknown>
    before_payload?: Record<string, unknown>
    after_payload?: Record<string, unknown>
    release_plan_payload?: Record<string, unknown>
    rollback_plan_payload?: Record<string, unknown>
    current_approver_role?: string | null
    manual_review_note?: string | null
  }): Promise<ReleaseChangeItem> =>
    unwrap(api.post<ApiEnvelope<ReleaseChangeItem>>('/api/v1/release/changes', payload)),

  operateReleaseChange: async (
    changeId: number,
    payload: {
      action: string
      note?: string | null
      scheduled_at?: string | null
      simulate_failure?: boolean
      failure_reason?: string | null
      trigger_rollback?: boolean
    },
  ): Promise<ReleaseChangeItem | ReleaseExecuteResponse> =>
    unwrap(api.post<ApiEnvelope<ReleaseChangeItem | ReleaseExecuteResponse>>(`/api/v1/release/changes/${changeId}/actions`, payload)),

  getReportsOverview: async (): Promise<ReportOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<ReportOverviewResponse>>('/api/v1/reports/overview')),

  getReportTemplates: async (): Promise<ReportTemplateListResponse> =>
    unwrap(api.get<ApiEnvelope<ReportTemplateListResponse>>('/api/v1/reports/templates')),

  getReportItems: async (params?: {
    q?: string
    kind?: string
    status?: string
    creator?: string
    scenario?: string
    tag?: string
    limit?: number
    offset?: number
  }): Promise<ReportListResponse> =>
    unwrap(api.get<ApiEnvelope<ReportListResponse>>('/api/v1/reports/items', { params })),

  getReportItemDetail: async (
    itemId: number,
    params?: {
      include_data?: boolean
      time_window_days?: number
      runtime_filters?: string
      saved_view_id?: number
    },
  ): Promise<ReportDetailResponse> =>
    unwrap(api.get<ApiEnvelope<ReportDetailResponse>>(`/api/v1/reports/items/${itemId}`, { params })),

  createReportItem: async (payload: {
    template_key?: string
    kind?: string
    name?: string
    description?: string | null
    scenario?: string | null
    status?: string
    is_personal?: boolean
    layout_payload?: Record<string, unknown>
    query_payload?: Record<string, unknown>
    filter_payload?: Record<string, unknown>
    refresh_payload?: Record<string, unknown>
    permission_payload?: Record<string, unknown>
    tags?: string[]
    change_note?: string | null
  }): Promise<ReportDashboardItem> =>
    unwrap(api.post<ApiEnvelope<ReportDashboardItem>>('/api/v1/reports/items', payload)),

  updateReportItem: async (
    itemId: number,
    payload: {
      kind?: string
      name?: string
      description?: string | null
      scenario?: string | null
      status?: string
      is_personal?: boolean
      layout_payload?: Record<string, unknown>
      query_payload?: Record<string, unknown>
      filter_payload?: Record<string, unknown>
      refresh_payload?: Record<string, unknown>
      permission_payload?: Record<string, unknown>
      tags?: string[]
      change_note?: string | null
    },
  ): Promise<ReportDashboardItem> =>
    unwrap(api.patch<ApiEnvelope<ReportDashboardItem>>(`/api/v1/reports/items/${itemId}`, payload)),

  operateReportItem: async (
    itemId: number,
    payload: {
      action: string
      note?: string | null
      clone_name?: string | null
      view_name?: string | null
      view_filter_payload?: Record<string, unknown>
      view_layout_override_payload?: Record<string, unknown>
      is_default_view?: boolean
      export_format?: string | null
      link_expires_hours?: number
      time_window_days?: number
      share_payload?: Record<string, unknown>
    },
  ): Promise<Record<string, unknown>> =>
    unwrap(api.post<ApiEnvelope<Record<string, unknown>>>(`/api/v1/reports/items/${itemId}/actions`, payload)),

  getMarketplaceOverview: async (): Promise<MarketplaceOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<MarketplaceOverviewResponse>>('/api/v1/marketplace/overview')),

  getMarketplaceProducts: async (params?: {
    q?: string
    status?: string
    visibility?: string
    owner?: string
    domain?: string
    tag?: string
    limit?: number
    offset?: number
  }): Promise<MarketplaceListResponse> =>
    unwrap(api.get<ApiEnvelope<MarketplaceListResponse>>('/api/v1/marketplace/products', { params })),

  getMarketplaceProductDetail: async (productId: number): Promise<MarketplaceDetailResponse> =>
    unwrap(api.get<ApiEnvelope<MarketplaceDetailResponse>>(`/api/v1/marketplace/products/${productId}`)),

  createMarketplaceProduct: async (payload: {
    product_key?: string
    name: string
    description?: string | null
    domain?: string | null
    category?: string | null
    status?: string
    visibility?: string
    schema_payload?: Record<string, unknown>
    asset_ids?: number[]
    tags?: string[]
    sla_payload?: Record<string, unknown>
    access_policy_payload?: Record<string, unknown>
    usage_payload?: Record<string, unknown>
    change_note?: string | null
  }): Promise<MarketplaceProductItem> =>
    unwrap(api.post<ApiEnvelope<MarketplaceProductItem>>('/api/v1/marketplace/products', payload)),

  updateMarketplaceProduct: async (
    productId: number,
    payload: {
      name?: string
      description?: string | null
      domain?: string | null
      category?: string | null
      status?: string
      visibility?: string
      schema_payload?: Record<string, unknown>
      asset_ids?: number[]
      tags?: string[]
      sla_payload?: Record<string, unknown>
      access_policy_payload?: Record<string, unknown>
      usage_payload?: Record<string, unknown>
      change_note?: string | null
    },
  ): Promise<MarketplaceProductItem> =>
    unwrap(api.patch<ApiEnvelope<MarketplaceProductItem>>(`/api/v1/marketplace/products/${productId}`, payload)),

  operateMarketplaceProduct: async (
    productId: number,
    payload: {
      action: string
      note?: string | null
      subscription_id?: number
      request_reason?: string | null
      expires_hours?: number
      usage_quota_payload?: Record<string, unknown>
    },
  ): Promise<Record<string, unknown>> =>
    unwrap(api.post<ApiEnvelope<Record<string, unknown>>>(`/api/v1/marketplace/products/${productId}/actions`, payload)),

  getIncidentOverview: async (): Promise<IncidentOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<IncidentOverviewResponse>>('/api/v1/incidents/overview')),

  getIncidentCases: async (params?: {
    q?: string
    status?: string
    severity?: string
    owner?: string
    assignee?: string
    source_type?: string
    limit?: number
    offset?: number
  }): Promise<IncidentListResponse> =>
    unwrap(api.get<ApiEnvelope<IncidentListResponse>>('/api/v1/incidents/cases', { params })),

  getIncidentCaseDetail: async (caseId: number): Promise<IncidentDetailResponse> =>
    unwrap(api.get<ApiEnvelope<IncidentDetailResponse>>(`/api/v1/incidents/cases/${caseId}`)),

  createIncidentCase: async (payload: {
    source_type: string
    source_id: string
    title: string
    summary?: string | null
    severity?: string
    assignee?: string | null
    runbook_doc_id?: number
    context_payload?: Record<string, unknown>
    impact_payload?: Record<string, unknown>
    resolution_payload?: Record<string, unknown>
    note?: string | null
  }): Promise<IncidentCaseItem> =>
    unwrap(api.post<ApiEnvelope<IncidentCaseItem>>('/api/v1/incidents/cases', payload)),

  updateIncidentCase: async (
    caseId: number,
    payload: {
      title?: string
      summary?: string | null
      severity?: string
      assignee?: string | null
      runbook_doc_id?: number
      context_payload?: Record<string, unknown>
      impact_payload?: Record<string, unknown>
      resolution_payload?: Record<string, unknown>
      note?: string | null
    },
  ): Promise<IncidentCaseItem> =>
    unwrap(api.patch<ApiEnvelope<IncidentCaseItem>>(`/api/v1/incidents/cases/${caseId}`, payload)),

  operateIncidentCase: async (
    caseId: number,
    payload: {
      action: string
      note?: string | null
      assignee?: string | null
      runbook_doc_id?: number
      impact_payload?: Record<string, unknown>
      resolution_payload?: Record<string, unknown>
    },
  ): Promise<IncidentCaseItem> =>
    unwrap(api.post<ApiEnvelope<IncidentCaseItem>>(`/api/v1/incidents/cases/${caseId}/actions`, payload)),

  getIngestionOverview: async (): Promise<IngestionOverviewResponse> =>
    unwrap(api.get<ApiEnvelope<IngestionOverviewResponse>>('/api/v1/ingestion/overview')),

  getIngestionOptions: async (): Promise<IngestionOptionsResponse> =>
    unwrap(api.get<ApiEnvelope<IngestionOptionsResponse>>('/api/v1/ingestion/options')),

  getIngestionChannels: async (params?: {
    q?: string
    platform?: string
    environment?: string
    status?: string
    limit?: number
    offset?: number
  }): Promise<IngestionChannelListResponse> =>
    unwrap(api.get<ApiEnvelope<IngestionChannelListResponse>>('/api/v1/ingestion/channels', { params })),

  getIngestionChannelDetail: async (channelId: number): Promise<IngestionChannelDetailResponse> =>
    unwrap(api.get<ApiEnvelope<IngestionChannelDetailResponse>>(`/api/v1/ingestion/channels/${channelId}`)),

  createIngestionChannel: async (payload: {
    platform: string
    app_name: string
    environment?: string
    status?: string
    app_id?: string
    endpoint_domain?: string
    endpoint_path?: string
    auth_mode?: string
    sampling_mode?: string
    sampling_rate?: number
    switches_payload?: Record<string, unknown>
    blocked_events?: string[]
    sdk_version?: string
    sdk_config_payload?: Record<string, unknown>
    quickstart_payload?: Record<string, unknown>
  }): Promise<IngestionChannelMutationResponse> =>
    unwrap(api.post<ApiEnvelope<IngestionChannelMutationResponse>>('/api/v1/ingestion/channels', payload)),

  updateIngestionChannel: async (
    channelId: number,
    payload: {
      app_name?: string
      environment?: string
      status?: string
      endpoint_domain?: string
      endpoint_path?: string
      auth_mode?: string
      sampling_mode?: string
      sampling_rate?: number
      switches_payload?: Record<string, unknown>
      blocked_events?: string[]
      sdk_version?: string
      sdk_config_payload?: Record<string, unknown>
      quickstart_payload?: Record<string, unknown>
    },
  ): Promise<IngestionChannelMutationResponse> =>
    unwrap(api.patch<ApiEnvelope<IngestionChannelMutationResponse>>(`/api/v1/ingestion/channels/${channelId}`, payload)),

  rotateIngestionChannelKey: async (
    channelId: number,
    payload?: { reason?: string },
  ): Promise<IngestionChannelMutationResponse> =>
    unwrap(api.post<ApiEnvelope<IngestionChannelMutationResponse>>(`/api/v1/ingestion/channels/${channelId}/rotate-key`, payload ?? {})),

  ingestGatewayEvent: async (
    ingestKey: string,
    payload: {
      app_id: string
      event_name: string
      event_ts?: string
      sdk_version?: string
      payload?: Record<string, unknown>
    },
  ): Promise<IngestionGatewayResponse> =>
    unwrap(
      api.post<ApiEnvelope<IngestionGatewayResponse>>('/api/v1/ingestion/gateway/events', payload, {
        headers: { 'X-INGEST-KEY': ingestKey },
      }),
    ),

  checkGovernance: async (
    eventId: number | null,
    name: string,
    description: string,
    properties: string,
  ): Promise<GovernanceResult> => {
    let parsedProperties: Record<string, unknown> = {}
    try {
      parsedProperties = JSON.parse(properties || '{}')
    } catch {
      parsedProperties = {}
    }

    return unwrap(
      api.post<ApiEnvelope<GovernanceResult>>('/api/v1/governance/check', {
        event_id: eventId,
        name,
        description,
        properties: parsedProperties,
      }),
    )
  },

  applyGovernanceSuggestions: async (
    checkId: number,
    payload: { event_id?: number | null; suggestion_indexes?: number[]; custom_patch?: Record<string, unknown> },
  ): Promise<GovernanceApplySuggestionsResponse> =>
    unwrap(
      api.post<ApiEnvelope<GovernanceApplySuggestionsResponse>>(
        `/api/v1/governance/${checkId}/apply-suggestions`,
        payload,
      ),
    ),

  getAuditLogs: async (params?: {
    q?: string
    action?: string
    entity_type?: string
    trace_id?: string
    user?: string
    status?: AuditLogStatus
    date_from?: string
    date_to?: string
    limit?: number
    offset?: number
  }): Promise<AuditLogListResponse> =>
    unwrap(
      api.get<ApiEnvelope<AuditLogListResponse>>('/api/v1/audit/logs', {
        params: { ...params, include_meta: true },
      }),
    ),

  getAuditLogDetail: async (id: number): Promise<AuditLogDetailResponse> =>
    unwrap(api.get<ApiEnvelope<AuditLogDetailResponse>>(`/api/v1/audit/logs/${id}`)),

  exportAuditLogs: async (payload: {
    format: 'csv' | 'json'
    q?: string
    action?: string
    entity_type?: string
    trace_id?: string
    user?: string
    status?: AuditLogStatus
    date_from?: string
    date_to?: string
  }): Promise<AuditLogExportResponse> =>
    unwrap(api.post<ApiEnvelope<AuditLogExportResponse>>('/api/v1/audit/logs/export', payload)),

  getPipelineProvisionOptions: async (): Promise<PipelineProvisionOptionsResponse> =>
    unwrap(api.get<ApiEnvelope<PipelineProvisionOptionsResponse>>('/api/v1/pipelines/provision-options')),

  provisionPipeline: async (payload: {
    event_code: string
    partitions?: number
    replication_factor?: number
    retention_hours?: number
    resource_tier?: string
    topic_prefix?: string
    job_name_template?: string
  }): Promise<Pipeline> =>
    unwrap(api.post<ApiEnvelope<Pipeline>>('/api/v1/pipelines/provision', payload)),

  getPipelines: async (params?: {
    q?: string
    status?: string
    event_code?: string
    limit?: number
  }): Promise<Pipeline[]> =>
    unwrap(api.get<ApiEnvelope<Pipeline[]>>('/api/v1/pipelines/', { params })),

  pausePipeline: async (id: number): Promise<Pipeline> =>
    unwrap(api.post<ApiEnvelope<Pipeline>>(`/api/v1/pipelines/${id}/pause`)),

  resumePipeline: async (id: number): Promise<Pipeline> =>
    unwrap(api.post<ApiEnvelope<Pipeline>>(`/api/v1/pipelines/${id}/resume`)),

  rollbackPipeline: async (id: number): Promise<Pipeline> =>
    unwrap(api.post<ApiEnvelope<Pipeline>>(`/api/v1/pipelines/${id}/rollback`)),

  syncPipeline: async (id: number): Promise<Pipeline> =>
    unwrap(api.post<ApiEnvelope<Pipeline>>(`/api/v1/pipelines/${id}/sync`)),

  getPipelineHistory: async (id: number): Promise<PipelineHistoryItem[]> =>
    unwrap(api.get<ApiEnvelope<PipelineHistoryItem[]>>(`/api/v1/pipelines/${id}/history`)),
}

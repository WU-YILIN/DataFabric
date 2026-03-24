import {
  type AnalysisPlanDetail,
  type ConflictItem,
  type GenerateAnalysisPlanPayload,
  type MetricCandidate,
} from '../services/api'

export type EvidenceTab = 'official' | 'historical' | 'field_facts'

export interface PlannerReviewRoute {
  owner_role: 'EDITOR' | 'APPROVER' | 'OWNER' | 'ADMIN'
  escalation_roles: Array<'EDITOR' | 'APPROVER' | 'OWNER' | 'ADMIN'>
}

export interface PlannerPrimaryRoute {
  conflict: ConflictItem
  route: PlannerReviewRoute
}

const elevatedTenantRoles = new Set(['OWNER', 'ADMIN'])

const rolePriority: Record<PlannerReviewRoute['owner_role'], number> = {
  EDITOR: 1,
  APPROVER: 2,
  OWNER: 3,
  ADMIN: 4,
}

const conflictPriority: Record<ConflictItem['conflict_type'], number> = {
  FIELD_FACT_MISMATCH: 1,
  HIGH_COST_REVIEW: 2,
  BUSINESS_DEFINITION_MISMATCH: 3,
  PERMISSION_BLOCKER: 4,
}

export function getPlannerReviewRoute(conflict: ConflictItem): PlannerReviewRoute {
  if (conflict.conflict_type === 'BUSINESS_DEFINITION_MISMATCH') {
    return {
      owner_role: 'APPROVER',
      escalation_roles: conflict.is_core_metric ? ['OWNER', 'ADMIN'] : [],
    }
  }

  if (conflict.conflict_type === 'FIELD_FACT_MISMATCH') {
    return {
      owner_role: 'EDITOR',
      escalation_roles: conflict.requires_cross_source_access ? ['ADMIN'] : [],
    }
  }

  if (conflict.conflict_type === 'PERMISSION_BLOCKER') {
    return {
      owner_role: 'ADMIN',
      escalation_roles: [],
    }
  }

  return {
    owner_role: 'APPROVER',
    escalation_roles: [],
  }
}

export function derivePrimaryReviewRoute(conflicts: ConflictItem[]): PlannerPrimaryRoute | null {
  if (conflicts.length === 0) {
    return null
  }

  return [...conflicts]
    .map((conflict) => ({
      conflict,
      route: getPlannerReviewRoute(conflict),
    }))
    .sort((left, right) => {
      const roleDelta = rolePriority[right.route.owner_role] - rolePriority[left.route.owner_role]
      if (roleDelta !== 0) {
        return roleDelta
      }

      const conflictDelta = conflictPriority[right.conflict.conflict_type] - conflictPriority[left.conflict.conflict_type]
      if (conflictDelta !== 0) {
        return conflictDelta
      }

      return right.route.escalation_roles.length - left.route.escalation_roles.length
    })[0]
}

export function canReviewAnalysisPlan(
  detail: Pick<AnalysisPlanDetail, 'status' | 'conflicts'>,
  roles: { projectRole?: string | null; tenantRole?: string | null },
): boolean {
  if (detail.status !== 'REVIEW_REQUIRED') {
    return false
  }

  const normalizedRoles = new Set(
    [roles.projectRole, roles.tenantRole]
      .filter(Boolean)
      .map((role) => String(role).toUpperCase()),
  )

  const primaryRoute = derivePrimaryReviewRoute(detail.conflicts)
  if (!primaryRoute) {
    return true
  }

  if ([...normalizedRoles].some((role) => elevatedTenantRoles.has(role))) {
    return true
  }

  const allowedRoles = new Set([primaryRoute.route.owner_role, ...primaryRoute.route.escalation_roles])
  return [...normalizedRoles].some((role) => allowedRoles.has(role as PlannerReviewRoute['owner_role']))
}

function createCandidates(question: string): MetricCandidate[] {
  const normalized = question.toLowerCase()
  const candidates: MetricCandidate[] = []

  if (normalized.includes('gmv')) {
    candidates.push({ metric_key: 'gmv', label: 'GMV', domain: 'commerce', is_core_metric: true })
  }
  if (normalized.includes('订单') || normalized.includes('order')) {
    candidates.push({ metric_key: 'paid_orders', label: 'Paid Orders', domain: 'commerce', is_core_metric: false })
  }
  if (normalized.includes('收入') || normalized.includes('revenue')) {
    candidates.push({ metric_key: 'revenue', label: 'Revenue', domain: 'finance', is_core_metric: true })
  }

  return candidates.length > 0
    ? candidates
    : [{ metric_key: 'analysis_target', label: 'Analysis Target', domain: 'general', is_core_metric: false }]
}

function createConflicts(question: string, candidates: MetricCandidate[]): ConflictItem[] {
  const normalized = question.toLowerCase()
  const conflicts: ConflictItem[] = []

  if (normalized.includes('gmv')) {
    conflicts.push({
      conflict_type: 'BUSINESS_DEFINITION_MISMATCH',
      summary: 'GMV 口径需要与官方定义和历史看板再次对齐。',
      metric_key: 'gmv',
      is_core_metric: true,
      requires_cross_source_access: false,
    })
  }
  if (normalized.includes('成本') || normalized.includes('cost')) {
    conflicts.push({
      conflict_type: 'HIGH_COST_REVIEW',
      summary: '预计执行成本超过安全阈值，需要审批人确认。',
      metric_key: candidates[0]?.metric_key ?? null,
      is_core_metric: false,
      requires_cross_source_access: false,
    })
  }
  if (normalized.includes('权限') || normalized.includes('跨源') || normalized.includes('cross-source')) {
    conflicts.push({
      conflict_type: 'PERMISSION_BLOCKER',
      summary: '查询涉及跨源访问，需管理员补齐权限。',
      metric_key: candidates[0]?.metric_key ?? null,
      is_core_metric: false,
      requires_cross_source_access: true,
    })
  }

  return conflicts
}

export function buildPlannerGeneratePayload(question: string): GenerateAnalysisPlanPayload {
  const metricCandidates = createCandidates(question)
  const conflicts = createConflicts(question, metricCandidates)
  const hasTimeScope = /(\d+\s*(天|日|周|月)|day|week|month)/i.test(question)

  return {
    question,
    question_weight: hasTimeScope ? 'LIGHT' : 'HEAVY',
    metric_candidates: metricCandidates,
    conflicts,
    review_requirements: conflicts.map((conflict) => ({
      code: `${conflict.conflict_type}_REVIEW`,
      summary: conflict.summary,
    })),
    evidence_bundle: {
      official: metricCandidates.map((candidate) => ({
        title: `${candidate.label} 官方口径`,
        summary: `围绕 ${candidate.label} 的标准定义与归属域`,
        content: `请优先校对 ${candidate.label} 的口径边界、时间窗口与过滤条件。`,
        doc_type: 'METRIC_DEFINITION',
        module: candidate.domain ?? 'analysis',
        tags: [candidate.metric_key],
        meta_payload: { metric_key: candidate.metric_key },
      })),
      historical: metricCandidates.map((candidate) => ({
        name: `${candidate.label} 历史复用线索`,
        description: `用于复查 ${candidate.label} 的既有看板或查询。`,
        kind: 'dashboard',
        scenario: 'analysis_planner',
        status: 'active',
        tags: [candidate.metric_key],
        query_payload: { metric_key: candidate.metric_key },
        cached_result_payload: { hint: 'reuse-first' },
      })),
      field_facts: metricCandidates.map((candidate) => ({
        name: `${candidate.metric_key}_field`,
        asset_type: 'COLUMN',
        source_system: 'warehouse',
        database_name: 'analytics',
        object_name: candidate.metric_key,
        domain: candidate.domain ?? 'analysis',
        description: `${candidate.label} 对应的字段事实线索`,
        schema_definition: { type: 'string' },
        tags: [candidate.metric_key],
      })),
    },
    result_service_plan: {
      result_kind: 'DATASET',
      freshness_mode: conflicts.length > 0 ? 'BATCH' : 'ON_DEMAND',
      publishable: conflicts.length === 0,
      recommended_engine: 'SPARK_SQL',
      reuse_key: `analysis-plan-${metricCandidates[0]?.metric_key ?? 'target'}`,
    },
  }
}

export function buildPlannerSummary(detail: AnalysisPlanDetail | null, question: string) {
  const questionSource = detail?.question ?? question
  const facts = [
    detail ? `当前状态为 ${detail.status}` : '等待提交问题后生成正式计划',
    detail ? `已归一化 ${detail.metric_candidates.length} 个候选指标` : '问题意图尚未归一化',
    /(\d+\s*(天|日|周|月)|day|week|month)/i.test(questionSource) ? '时间范围已在问题中给出' : '时间范围仍需补齐',
  ]
  const candidates = detail
    ? detail.metric_candidates.map((candidate) => `${candidate.label}${candidate.is_core_metric ? '（核心）' : ''}`)
    : createCandidates(questionSource).map((candidate) => `${candidate.label}${candidate.is_core_metric ? '（核心）' : ''}`)
  const missing = detail?.conflicts.length
    ? detail.conflicts.map((conflict) => conflict.summary)
    : ['优先复用官方定义、历史结果与字段事实，当前暂不开放执行动作。']

  return { facts, candidates, missing }
}

export function plannerStatusTone(status: string) {
  if (status === 'REVIEW_CONFIRMED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'REJECTED') return 'bg-rose-100 text-rose-700'
  if (status === 'REVIEW_REQUIRED') return 'bg-amber-100 text-amber-700'
  return 'bg-slate-100 text-slate-700'
}

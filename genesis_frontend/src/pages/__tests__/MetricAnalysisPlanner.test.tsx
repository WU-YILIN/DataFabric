import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import {
  GenesisApi,
  type AnalysisPlanDetail,
  type AnalysisPlanListResponse,
  type AnalysisPlanSummary,
  type ConflictItem,
  type MetricCandidate,
} from '../../services/api'
import MetricAnalysisPlanner from '../MetricAnalysisPlanner'
import { canReviewAnalysisPlan, derivePrimaryReviewRoute } from '../metricAnalysisPlanner.helpers'

const mockUseSession = vi.fn()

vi.mock('../../auth/session', () => ({
  useSession: () => mockUseSession(),
}))

const sampleCandidates: MetricCandidate[] = [
  {
    metric_key: 'gmv',
    label: 'GMV',
    domain: 'commerce',
    is_core_metric: true,
  },
  {
    metric_key: 'paid_orders',
    label: 'Paid Orders',
    domain: 'commerce',
    is_core_metric: false,
  },
]

const samplePlanDetail: AnalysisPlanDetail = {
  id: 42,
  project_id: 7,
  tenant_id: 3,
  question: '请规划30天付费订单与GMV指标',
  status: 'REVIEW_REQUIRED',
  question_weight: 'LIGHT',
  metric_candidates: sampleCandidates,
  conflicts: [
    {
      conflict_type: 'BUSINESS_DEFINITION_MISMATCH',
      summary: '收入口径与增长字典存在冲突',
      metric_key: 'gmv',
      is_core_metric: true,
      requires_cross_source_access: false,
    },
  ],
  review_requirements: [
    {
      code: 'APPROVER_SIGN_OFF',
      summary: '需要业务审批人确认',
    },
  ],
  evidence_bundle: {
    official: [
      {
        title: '收入定义',
        summary: '权威指标口径',
        content: 'Revenue is recognized net of refunds.',
        doc_type: 'METRIC_DEFINITION',
        module: 'finance',
        tags: ['revenue'],
        meta_payload: { document_id: 'doc-42' },
      },
    ],
    historical: [
      {
        name: 'Weekly revenue dashboard',
        description: 'Prior quarter planning reference',
        kind: 'dashboard',
        scenario: 'quarterly_review',
        status: 'active',
        tags: ['revenue'],
        query_payload: { dashboard_id: 'dash-1' },
        cached_result_payload: { rows: 12 },
      },
    ],
    field_facts: [
      {
        name: 'orders.gmv',
        asset_type: 'COLUMN',
        source_system: 'warehouse',
        database_name: 'analytics',
        object_name: 'orders',
        domain: 'commerce',
        description: 'Schema field metadata',
        schema_definition: { type: 'decimal' },
        tags: ['fact'],
      },
    ],
  },
  result_service_plan: {
    result_kind: 'DATASET',
    freshness_mode: 'BATCH',
    publishable: true,
    recommended_engine: 'SPARK_SQL',
    reuse_key: 'metric-plan-gmv',
  },
  collaboration_workflow_id: 9001,
  created_at: '2026-03-24T10:00:00Z',
  updated_at: '2026-03-24T10:05:00Z',
}

const samplePlanSummary: AnalysisPlanSummary = {
  id: samplePlanDetail.id,
  project_id: samplePlanDetail.project_id,
  tenant_id: samplePlanDetail.tenant_id,
  question: samplePlanDetail.question,
  status: samplePlanDetail.status,
  question_weight: samplePlanDetail.question_weight,
  metric_candidates: samplePlanDetail.metric_candidates,
  conflicts: samplePlanDetail.conflicts,
  review_requirements: samplePlanDetail.review_requirements,
  evidence_bundle: samplePlanDetail.evidence_bundle,
  result_service_plan: samplePlanDetail.result_service_plan,
  collaboration_workflow_id: samplePlanDetail.collaboration_workflow_id,
  created_at: samplePlanDetail.created_at,
  updated_at: samplePlanDetail.updated_at,
}

const reviewedPlanDetail: AnalysisPlanDetail = {
  ...samplePlanDetail,
  status: 'REVIEW_CONFIRMED',
  updated_at: '2026-03-24T10:08:00Z',
}

const emptyEvidencePlanDetail: AnalysisPlanDetail = {
  ...samplePlanDetail,
  conflicts: [
    {
      conflict_type: 'BUSINESS_DEFINITION_MISMATCH',
      summary: '官方定义与历史复用线索存在来源冲突',
      metric_key: 'gmv',
      is_core_metric: true,
      requires_cross_source_access: false,
    },
  ],
  evidence_bundle: {
    official: [],
    historical: [],
    field_facts: [],
  },
}

const blockedConflict: ConflictItem = {
  conflict_type: 'HIGH_COST_REVIEW',
  summary: '预计执行成本超过安全阈值',
  metric_key: 'gmv',
  is_core_metric: false,
  requires_cross_source_access: false,
}

const permissionConflict: ConflictItem = {
  conflict_type: 'PERMISSION_BLOCKER',
  summary: '跨源权限待管理员确认',
  metric_key: 'gmv',
  is_core_metric: false,
  requires_cross_source_access: true,
}

function renderPlanner() {
  return render(
    <MemoryRouter>
      <MetricAnalysisPlanner />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseSession.mockReturnValue({
    activeProject: { id: 7, name: 'Planner Project', role: 'APPROVER' },
    activeTenant: { id: 3, name: 'Planner Tenant', slug: 'planner', status: 'ACTIVE', role: 'MEMBER', projects: [] },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  mockUseSession.mockReset()
})

describe('MetricAnalysisPlanner page', () => {
  it('allows OWNER and ADMIN to override planner review restrictions', () => {
    expect(
      canReviewAnalysisPlan(
        { ...samplePlanDetail, conflicts: [blockedConflict] },
        { projectRole: 'VIEWER', tenantRole: 'ADMIN' },
      ),
    ).toBe(true)

    expect(
      canReviewAnalysisPlan(
        { ...samplePlanDetail, conflicts: [permissionConflict] },
        { projectRole: 'OWNER', tenantRole: 'MEMBER' },
      ),
    ).toBe(true)
  })

  it('chooses the highest-priority route when multiple conflicts exist', () => {
    const route = derivePrimaryReviewRoute([
      {
        conflict_type: 'FIELD_FACT_MISMATCH',
        summary: '字段事实需要编辑确认',
        metric_key: 'paid_orders',
        is_core_metric: false,
        requires_cross_source_access: false,
      },
      permissionConflict,
    ])

    expect(route?.conflict.conflict_type).toBe('PERMISSION_BLOCKER')
    expect(route?.route.owner_role).toBe('ADMIN')
  })

  it('returns no route for no-conflict plans and permits review when no route is required', () => {
    expect(derivePrimaryReviewRoute([])).toBeNull()
    expect(
      canReviewAnalysisPlan(
        { ...samplePlanDetail, conflicts: [] },
        { projectRole: 'VIEWER', tenantRole: 'MEMBER' },
      ),
    ).toBe(true)
  })

  it('renders generated candidates and the conflict banner on the real page', async () => {
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({ items: [], total: 0 })
    vi.spyOn(GenesisApi, 'generateAnalysisPlan').mockResolvedValue(samplePlanSummary)
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(samplePlanDetail)

    renderPlanner()

    await userEvent.type(screen.getByLabelText('问题输入'), samplePlanDetail.question)
    await userEvent.click(screen.getByRole('button', { name: '生成分析计划' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('待确认冲突')
    expect(screen.getByRole('alert')).toHaveTextContent(samplePlanDetail.conflicts[0].summary)
    expect(screen.getByRole('region', { name: '候选指标' })).toHaveTextContent('GMV')
    expect(screen.getByRole('region', { name: '候选指标' })).toHaveTextContent('Paid Orders')
    expect(screen.getByRole('heading', { name: '已确认事实' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '执行线索' })).toBeInTheDocument()
  })

  it('does not render execution actions in v1', async () => {
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({ items: [samplePlanSummary], total: 1 })
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(samplePlanDetail)

    renderPlanner()

    await screen.findByText(samplePlanDetail.question)
    expect(screen.getByText(samplePlanDetail.result_service_plan.result_kind)).toBeInTheDocument()
    expect(screen.getByText(samplePlanDetail.result_service_plan.freshness_mode)).toBeInTheDocument()
    expect(screen.getByText(samplePlanDetail.result_service_plan.recommended_engine)).toBeInTheDocument()
    expect(screen.getByText(samplePlanDetail.result_service_plan.reuse_key)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /执行|Execute/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /发布|Publish/i })).not.toBeInTheDocument()
  })

  it('renders explicit source-conflict and no-evidence empty states', async () => {
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [{ ...samplePlanSummary, conflicts: emptyEvidencePlanDetail.conflicts, evidence_bundle: emptyEvidencePlanDetail.evidence_bundle }],
      total: 1,
    })
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(emptyEvidencePlanDetail)

    renderPlanner()

    await screen.findByText(emptyEvidencePlanDetail.question)
    expect(screen.getByText('发现来源冲突')).toBeInTheDocument()
    expect(screen.getByText('请先补充一致的官方定义、历史复用或字段事实，再继续复核。')).toBeInTheDocument()
    expect(screen.getByText('暂无官方定义证据，请先补充权威口径。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '历史复用' }))
    expect(screen.getByText('暂无历史复用线索，请补充可复用结果。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '字段事实' }))
    expect(screen.getByText('暂无字段事实，请补充字段元数据或血缘线索。')).toBeInTheDocument()
  })

  it('surfaces a high-cost review badge and messaging', async () => {
    const highCostPlan = {
      ...samplePlanDetail,
      conflicts: [blockedConflict],
    }

    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [{ ...samplePlanSummary, conflicts: [blockedConflict] }],
      total: 1,
    })
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(highCostPlan)

    renderPlanner()

    await screen.findByText(samplePlanDetail.question)
    expect(screen.getByText('高成本复核')).toBeInTheDocument()
    expect(screen.getByText('预计执行成本超过安全阈值，v1 仅保留规划与复核，不提供执行入口。')).toBeInTheDocument()
  })

  it('hides confirm action for a low-privilege user on blocked review plans', async () => {
    mockUseSession.mockReturnValue({
      activeProject: { id: 7, name: 'Planner Project', role: 'VIEWER' },
      activeTenant: { id: 3, name: 'Planner Tenant', slug: 'planner', status: 'ACTIVE', role: 'MEMBER', projects: [] },
    })
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [
        {
          ...samplePlanSummary,
          conflicts: [
            {
              conflict_type: 'HIGH_COST_REVIEW',
              summary: '预计执行成本超过安全阈值',
              metric_key: 'gmv',
              is_core_metric: false,
              requires_cross_source_access: false,
            },
          ],
        },
      ],
      total: 1,
    } satisfies AnalysisPlanListResponse)
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue({
      ...samplePlanDetail,
      conflicts: [
        {
          conflict_type: 'HIGH_COST_REVIEW',
          summary: '预计执行成本超过安全阈值',
          metric_key: 'gmv',
          is_core_metric: false,
          requires_cross_source_access: false,
        },
      ],
    })

    renderPlanner()

    await screen.findByText('当前角色无法确认该方案，请走协作复核链路。')
    expect(screen.queryByRole('button', { name: '确认方案' })).not.toBeInTheDocument()
    expect(screen.getByText('当前角色无法确认该方案，请走协作复核链路。')).toBeInTheDocument()
  })

  it('shows a detail-loading error when selecting another plan fails', async () => {
    const secondaryPlan = {
      ...samplePlanSummary,
      id: 84,
      question: '请规划跨域成本与订单复核',
      conflicts: [blockedConflict],
    }

    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [samplePlanSummary, secondaryPlan],
      total: 2,
    })
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockImplementation(async (planId: number) => {
      if (planId === samplePlanSummary.id) {
        return samplePlanDetail
      }
      throw new Error('detail failed')
    })

    renderPlanner()

    await screen.findByText(samplePlanDetail.question)
    await userEvent.click(screen.getByRole('button', { name: new RegExp(secondaryPlan.question) }))

    expect(await screen.findByText('加载分析规划详情失败')).toBeInTheDocument()
  })

  it('uses GenesisApi.reviewAnalysisPlan and updates page state', async () => {
    const reviewSpy = vi.spyOn(GenesisApi, 'reviewAnalysisPlan').mockResolvedValue(reviewedPlanDetail)
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [samplePlanSummary],
      total: 1,
    } satisfies AnalysisPlanListResponse)
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(samplePlanDetail)

    renderPlanner()

    await screen.findByRole('button', { name: '确认方案' })
    await userEvent.click(screen.getByRole('button', { name: '确认方案' }))

    expect(reviewSpy).toHaveBeenCalledWith(samplePlanDetail.id, { action: 'CONFIRM', note: null })
    await waitFor(() => expect(screen.getAllByText('REVIEW_CONFIRMED').length).toBeGreaterThan(0))
    expect(screen.getByText('已完成确认，可进入后续结果交付编排。')).toBeInTheDocument()
  })

  it('disables review actions while the mutation is in flight', async () => {
    let resolveReview: ((value: AnalysisPlanDetail) => void) | undefined
    vi.spyOn(GenesisApi, 'reviewAnalysisPlan').mockImplementation(
      () =>
        new Promise<AnalysisPlanDetail>((resolve) => {
          resolveReview = resolve
        }),
    )
    vi.spyOn(GenesisApi, 'getAnalysisPlans').mockResolvedValue({
      items: [samplePlanSummary],
      total: 1,
    } satisfies AnalysisPlanListResponse)
    vi.spyOn(GenesisApi, 'getAnalysisPlanDetail').mockResolvedValue(samplePlanDetail)

    renderPlanner()

    const confirmButton = await screen.findByRole('button', { name: '确认方案' })
    const rejectButton = screen.getByRole('button', { name: '退回复核' })
    await userEvent.click(confirmButton)

    expect(screen.getByRole('button', { name: '提交中...' })).toBeDisabled()
    expect(rejectButton).toBeDisabled()

    expect(resolveReview).toBeDefined()
    resolveReview!(reviewedPlanDetail)
    await waitFor(() => expect(screen.getByText('已完成确认，可进入后续结果交付编排。')).toBeInTheDocument())
  })
})

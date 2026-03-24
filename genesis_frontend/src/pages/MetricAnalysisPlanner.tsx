import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'

import { useSession } from '../auth/session'
import {
  GenesisApi,
  type AnalysisPlanDetail,
  type AnalysisPlanSummary,
  type ReviewAnalysisPlanPayload,
} from '../services/api'
import {
  buildPlannerGeneratePayload,
  buildPlannerSummary,
  canReviewAnalysisPlan,
  derivePrimaryReviewRoute,
  plannerStatusTone,
  type EvidenceTab,
} from './metricAnalysisPlanner.helpers'

const emptyEvidenceMessage: Record<EvidenceTab, string> = {
  official: '暂无官方定义证据，请先补充权威口径。',
  historical: '暂无历史复用线索，请补充可复用结果。',
  field_facts: '暂无字段事实，请补充字段元数据或血缘线索。',
}

const MetricAnalysisPlanner = () => {
  const { activeProject, activeTenant } = useSession()
  const [question, setQuestion] = useState('')
  const [plans, setPlans] = useState<AnalysisPlanSummary[]>([])
  const [detail, setDetail] = useState<AnalysisPlanDetail | null>(null)
  const [activeTab, setActiveTab] = useState<EvidenceTab>('official')
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      setLoadingList(true)
      setError(null)
      try {
        const response = await GenesisApi.getAnalysisPlans()
        setPlans(response.items)
        if (response.items[0]) {
          const nextDetail = await GenesisApi.getAnalysisPlanDetail(response.items[0].id)
          setDetail(nextDetail)
          setQuestion(nextDetail.question)
        }
      } catch (nextError: any) {
        setError(nextError?.response?.data?.message ?? '加载分析规划失败')
      } finally {
        setLoadingList(false)
      }
    })()
  }, [])

  const primaryRoute = useMemo(() => derivePrimaryReviewRoute(detail?.conflicts ?? []), [detail])

  const canReview = useMemo(() => {
    if (!detail) {
      return false
    }
    return canReviewAnalysisPlan(detail, {
      projectRole: activeProject?.role,
      tenantRole: activeTenant?.role,
    })
  }, [activeProject?.role, activeTenant?.role, detail])

  const summary = useMemo(() => buildPlannerSummary(detail, question), [detail, question])

  const evidenceItems = detail?.evidence_bundle?.[activeTab] ?? []
  const hasSourceConflict = (detail?.conflicts ?? []).some((conflict) => conflict.conflict_type === 'BUSINESS_DEFINITION_MISMATCH')
  const hasHighCostConflict = (detail?.conflicts ?? []).some((conflict) => conflict.conflict_type === 'HIGH_COST_REVIEW')

  const selectPlan = async (planId: number) => {
    setLoadingDetail(true)
    setError(null)
    try {
      const nextDetail = await GenesisApi.getAnalysisPlanDetail(planId)
      setDetail(nextDetail)
      setQuestion(nextDetail.question)
    } catch (nextError: any) {
      setError(nextError?.response?.data?.message ?? '加载分析规划详情失败')
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleGenerate = async () => {
    if (!question.trim()) {
      setError('请输入需要规划的业务问题')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      const created = await GenesisApi.generateAnalysisPlan(buildPlannerGeneratePayload(question.trim()))
      const nextDetail = await GenesisApi.getAnalysisPlanDetail(created.id)
      setDetail(nextDetail)
      setPlans((current) => [created, ...current.filter((item) => item.id !== created.id)])
      setActiveTab('official')
    } catch (nextError: any) {
      setError(nextError?.response?.data?.message ?? '生成分析计划失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReview = async (payload: ReviewAnalysisPlanPayload) => {
    if (!detail) {
      return
    }

    setReviewing(true)
    setError(null)
    try {
      const reviewed = await GenesisApi.reviewAnalysisPlan(detail.id, payload)
      setDetail(reviewed)
      setPlans((current) =>
        current.map((plan) =>
          plan.id === reviewed.id
            ? {
                ...plan,
                status: reviewed.status,
                updated_at: reviewed.updated_at,
              }
            : plan,
        ),
      )
    } catch (nextError: any) {
      setError(nextError?.response?.data?.message ?? '提交复核动作失败')
    } finally {
      setReviewing(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <header className="rounded-3xl border border-slate-200 bg-white/85 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Analysis Planner</p>
            <h2 className="text-3xl font-bold tracking-tight text-slate-900">指标分析规划</h2>
            <p className="max-w-3xl text-sm text-slate-600">
              用单次提交沉淀问题理解、指标候选、证据线索与复核路由，先完成结构化规划，再决定是否进入协作复核。
            </p>
          </div>
          {detail ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <div>当前计划 #{detail.id}</div>
              <div className="mt-2 flex items-center gap-2">
                <span className={clsx('rounded-full px-2.5 py-1 text-xs font-semibold', plannerStatusTone(detail.status))}>{detail.status}</span>
                <span>{detail.question_weight}</span>
              </div>
            </div>
          ) : null}
        </div>
      </header>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-4 rounded-3xl border border-slate-200 bg-white/80 p-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">历史规划</h3>
            <p className="mt-1 text-xs text-slate-500">保留最近生成或已进入复核的分析计划。</p>
          </div>
            <div className="space-y-2">
              {loadingList ? <p className="text-sm text-slate-500">加载中...</p> : null}
              {loadingDetail ? <p className="text-sm text-slate-500">规划详情加载中...</p> : null}
              {!loadingList && plans.length === 0 ? <p className="text-sm text-slate-500">暂无历史规划，可先提交一个问题。</p> : null}
              {plans.map((plan) => (
              <button
                key={plan.id}
                type="button"
                onClick={() => void selectPlan(plan.id)}
                className={clsx(
                  'w-full rounded-2xl border px-3 py-3 text-left transition',
                  detail?.id === plan.id ? 'border-cyan-500 bg-cyan-50' : 'border-slate-200 bg-white hover:border-slate-300',
                )}
              >
                <div className="line-clamp-2 text-sm font-semibold text-slate-900">{plan.question}</div>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>{plan.metric_candidates.length} 个候选</span>
                    <span className={clsx('rounded-full px-2 py-0.5 font-semibold', plannerStatusTone(plan.status))}>{plan.status}</span>
                  </div>
                </button>
              ))}
          </div>
        </aside>

        <div className="space-y-5">
          <section className="rounded-3xl border border-slate-200 bg-white/85 p-5">
            <label htmlFor="planner-question" className="mb-2 block text-sm font-semibold text-slate-900">
              问题输入
            </label>
            <textarea
              id="planner-question"
              rows={5}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：请规划30天付费订单与GMV指标，并说明需要哪条复核链路。"
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-cyan-500"
            />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500">v1 仅生成结构化规划与复核建议，不直接触发执行或发布动作。</p>
              <button
                type="button"
                onClick={() => void handleGenerate()}
                disabled={submitting}
                className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
              >
                {submitting ? '生成中...' : '生成分析计划'}
              </button>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5">
              <h3 className="text-lg font-semibold text-slate-900">已确认事实</h3>
              <ul className="mt-3 space-y-2 text-sm text-slate-600">
                {summary.facts.map((item) => (
                  <li key={item} className="rounded-2xl bg-slate-50 px-3 py-2">{item}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5">
              <h3 className="text-lg font-semibold text-slate-900">候选判断</h3>
              <ul className="mt-3 space-y-2 text-sm text-slate-600">
                {summary.candidates.map((item) => (
                  <li key={item} className="rounded-2xl bg-slate-50 px-3 py-2">{item}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5">
              <h3 className="text-lg font-semibold text-slate-900">执行线索</h3>
              <ul className="mt-3 space-y-2 text-sm text-slate-600">
                {summary.missing.map((item) => (
                  <li key={item} className="rounded-2xl bg-slate-50 px-3 py-2">{item}</li>
                ))}
              </ul>
            </div>
          </section>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-slate-900">候选指标与证据</h3>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    ['official', '官方定义'],
                    ['historical', '历史复用'],
                    ['field_facts', '字段事实'],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setActiveTab(key as EvidenceTab)}
                      className={clsx(
                        'rounded-full px-3 py-1.5 font-semibold transition',
                        activeTab === key ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <section aria-label="候选指标" className="mt-4 space-y-3">
                {(detail?.metric_candidates ?? []).map((candidate) => (
                  <div key={candidate.metric_key} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-slate-900">{candidate.label}</div>
                        <div className="text-xs text-slate-500">{candidate.metric_key} · {candidate.domain ?? 'general'}</div>
                      </div>
                      {candidate.is_core_metric ? <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-700">核心指标</span> : null}
                    </div>
                  </div>
                ))}
                {!detail?.metric_candidates.length ? <p className="text-sm text-slate-500">先提交问题后展示候选指标。</p> : null}
              </section>

              <div className="mt-5 space-y-3">
                {hasSourceConflict ? (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    <div className="font-semibold">发现来源冲突</div>
                    <p className="mt-1 text-amber-800">请先补充一致的官方定义、历史复用或字段事实，再继续复核。</p>
                  </div>
                ) : null}
                {evidenceItems.length === 0 ? <p className="text-sm text-slate-500">{emptyEvidenceMessage[activeTab]}</p> : null}
                {evidenceItems.map((item, index) => (
                  <div key={`${activeTab}-${index}`} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    {'title' in item ? (
                      <>
                        <div className="font-semibold text-slate-900">{item.title}</div>
                        <div className="mt-1">{item.summary}</div>
                      </>
                    ) : null}
                    {'name' in item ? <div className="font-semibold text-slate-900">{item.name}</div> : null}
                    {'description' in item ? <div className="mt-1">{item.description}</div> : null}
                    {'content' in item ? <div className="mt-1 line-clamp-3 text-slate-500">{item.content}</div> : null}
                    {'source_system' in item ? <div className="mt-1 text-slate-500">{item.source_system} · {item.database_name}.{item.object_name}</div> : null}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <section className="rounded-3xl border border-slate-200 bg-white/85 p-5">
                <h3 className="text-lg font-semibold text-slate-900">复核与路由建议</h3>
                {detail?.conflicts.length ? (
                  <div role="alert" className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
                    <div className="font-semibold">待确认冲突</div>
                    <ul className="mt-2 space-y-2">
                      {detail.conflicts.map((conflict) => (
                        <li key={`${conflict.conflict_type}-${conflict.summary}`}>{conflict.summary}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-700">
                    当前方案未检测到阻塞冲突，可按结果交付计划继续推进。
                  </div>
                )}

                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
                  <div className="font-semibold text-slate-900">推荐复核角色</div>
                  <div className="mt-2">{primaryRoute ? primaryRoute.route.owner_role : 'NO_REVIEW_REQUIRED'}</div>
                  {hasHighCostConflict ? (
                    <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800">
                      <div className="inline-flex items-center rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700">高成本复核</div>
                      <p className="mt-2">预计执行成本超过安全阈值，v1 仅保留规划与复核，不提供执行入口。</p>
                    </div>
                  ) : null}
                  {primaryRoute?.route.escalation_roles.length ? (
                    <div className="mt-2 text-xs text-slate-500">升级链路：{primaryRoute.route.escalation_roles.join(' -> ')}</div>
                  ) : null}
                  {detail?.collaboration_workflow_id ? (
                    <Link to="/collaboration" className="mt-3 inline-flex text-sm font-semibold text-cyan-700 hover:text-cyan-800">
                      查看协作工作流 #{detail.collaboration_workflow_id}
                    </Link>
                  ) : null}
                </div>

                {detail?.status === 'REVIEW_REQUIRED' ? (
                  canReview ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={reviewing}
                        onClick={() => void handleReview({ action: 'CONFIRM', note: null })}
                        className="rounded-2xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
                      >
                        {reviewing ? '提交中...' : '确认方案'}
                      </button>
                      <button
                        type="button"
                        disabled={reviewing}
                        onClick={() => void handleReview({ action: 'REJECT', note: null })}
                        className="rounded-2xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        退回复核
                      </button>
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-slate-500">当前角色无法确认该方案，请走协作复核链路。</p>
                  )
                ) : null}

                {detail?.status === 'REVIEW_CONFIRMED' ? <p className="mt-4 text-sm font-medium text-emerald-700">已完成确认，可进入后续结果交付编排。</p> : null}
              </section>

              <section className="rounded-3xl border border-slate-200 bg-white/85 p-5">
                <h3 className="text-lg font-semibold text-slate-900">结果服务计划</h3>
                {detail ? (
                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-600">
                    <div className="rounded-2xl bg-slate-50 px-3 py-3">
                      <div className="text-xs text-slate-500">结果类型</div>
                      <div className="mt-1 font-semibold text-slate-900">{detail.result_service_plan.result_kind}</div>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-3 py-3">
                      <div className="text-xs text-slate-500">刷新策略</div>
                      <div className="mt-1 font-semibold text-slate-900">{detail.result_service_plan.freshness_mode}</div>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-3 py-3">
                      <div className="text-xs text-slate-500">推荐引擎</div>
                      <div className="mt-1 font-semibold text-slate-900">{detail.result_service_plan.recommended_engine}</div>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-3 py-3">
                      <div className="text-xs text-slate-500">复用键</div>
                      <div className="mt-1 font-semibold text-slate-900">{detail.result_service_plan.reuse_key}</div>
                    </div>
                    <div className="col-span-2 rounded-2xl border border-dashed border-slate-200 px-3 py-3 text-xs text-slate-500">
                      发布与执行动作在 v1 中保持隐藏，仅展示结果交付建议与复核上下文。
                    </div>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">生成计划后展示结果服务编排建议。</p>
                )}
              </section>
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}

export default MetricAnalysisPlanner

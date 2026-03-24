import { useEffect, useMemo, useState } from 'react'
import { Bot, FileSearch, Send, Workflow } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import {
  GenesisApi,
  type FabricListResponse,
  type FabricQueryRunDetail,
  type FabricQueryRunListItem,
  type FabricQuerySubmission,
  type FabricUpdateSemantic,
} from '../services/api'
import {
  FabricBadge,
  FabricEmptyState,
  FabricFilterSelect,
  FabricPageHeader,
  FabricPager,
  FabricSearchInput,
  FabricSection,
  FabricStatCard,
} from '../components/fabricUi'

const PLANNER_PAGE_SIZE = 8
const UPDATE_PAGE_SIZE = 10
const STARTER_QUESTIONS = [
  '最近30天华东订单金额趋势应该优先走哪条路径？',
  '请规划一条支付月报的执行计划，并说明是否需要异步执行。',
  '分析用户近90天复购时，应该先命中记忆、契约还是热点工件？',
]

type PlannerTab = 'planner' | 'update-semantics'

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function joinList(values?: string[] | null) {
  return values && values.length > 0 ? values.join('、') : '未提供'
}

function payloadArray<T = Record<string, unknown>>(payload: Record<string, unknown> | undefined, key: string) {
  const value = payload?.[key]
  return Array.isArray(value) ? (value as T[]) : []
}

export default function FabricPlanner() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = (searchParams.get('tab') as PlannerTab) || 'planner'

  const [question, setQuestion] = useState(STARTER_QUESTIONS[0])
  const [latencyTarget, setLatencyTarget] = useState(800)
  const [loadingSubmit, setLoadingSubmit] = useState(false)
  const [submission, setSubmission] = useState<FabricQuerySubmission | null>(null)
  const [selectedRunDetail, setSelectedRunDetail] = useState<FabricQueryRunDetail | null>(null)

  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('ALL')
  const [intentType, setIntentType] = useState('ALL')
  const [selectedPath, setSelectedPath] = useState('ALL')
  const [offset, setOffset] = useState(0)
  const [runs, setRuns] = useState<FabricListResponse<FabricQueryRunListItem> | null>(null)
  const [loadingRuns, setLoadingRuns] = useState(true)

  const [updateQuery, setUpdateQuery] = useState('')
  const [updateMode, setUpdateMode] = useState('ALL')
  const [updateOffset, setUpdateOffset] = useState(0)
  const [updateResponse, setUpdateResponse] = useState<FabricListResponse<FabricUpdateSemantic> | null>(null)
  const [loadingUpdates, setLoadingUpdates] = useState(false)

  const switchTab = (tab: PlannerTab) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next)
  }

  const loadRuns = async () => {
    setLoadingRuns(true)
    try {
      const next = await GenesisApi.getFabricQueryRuns({
        q: query.trim() || undefined,
        status: status === 'ALL' ? undefined : status,
        intent_type: intentType === 'ALL' ? undefined : intentType,
        selected_path: selectedPath === 'ALL' ? undefined : selectedPath,
        limit: PLANNER_PAGE_SIZE,
        offset,
      })
      setRuns(next)
      if (!selectedRunDetail && next.items.length > 0) {
        const detail = await GenesisApi.getFabricQueryRunDetail(next.items[0].id)
        setSelectedRunDetail(detail)
      }
    } finally {
      setLoadingRuns(false)
    }
  }

  const loadRunDetail = async (runId: number) => {
    const detail = await GenesisApi.getFabricQueryRunDetail(runId)
    setSelectedRunDetail(detail)
  }

  const loadUpdateSemantics = async () => {
    setLoadingUpdates(true)
    try {
      const next = await GenesisApi.getFabricUpdateSemantics({
        q: updateQuery.trim() || undefined,
        mode: updateMode === 'ALL' ? undefined : updateMode,
        limit: UPDATE_PAGE_SIZE,
        offset: updateOffset,
      })
      setUpdateResponse(next)
    } finally {
      setLoadingUpdates(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'planner') void loadRuns()
  }, [activeTab, query, status, intentType, selectedPath, offset])

  useEffect(() => {
    if (activeTab === 'update-semantics') void loadUpdateSemantics()
  }, [activeTab, updateQuery, updateMode, updateOffset])

  const submitPlan = async () => {
    if (!question.trim()) return
    setLoadingSubmit(true)
    try {
      const next = await GenesisApi.submitFabricQuery({
        question: question.trim(),
        latency_target_ms: latencyTarget,
      })
      setSubmission(next)
      await loadRunDetail(next.run.id)
      await loadRuns()
    } finally {
      setLoadingSubmit(false)
    }
  }

  const matchedSources = useMemo(
    () => payloadArray<{ source_name?: string; source_type?: string; heat_level?: string }>(selectedRunDetail?.plan?.matched_payload, 'sources'),
    [selectedRunDetail],
  )
  const matchedMemories = useMemo(
    () => payloadArray<{ title?: string; module?: string; status?: string }>(selectedRunDetail?.plan?.matched_payload, 'memories'),
    [selectedRunDetail],
  )
  const matchedContracts = useMemo(
    () => payloadArray<{ contract_name?: string; event_code?: string; serving_status?: string }>(selectedRunDetail?.plan?.matched_payload, 'contracts'),
    [selectedRunDetail],
  )

  const updateItems = updateResponse?.items ?? []
  const updateModes = [
    { label: '全部模式', value: 'ALL' },
    ...((updateResponse?.facets?.modes as string[] | undefined) ?? []).map((value) => ({ label: value, value })),
  ]

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="查询规划"
        title="策略中心与查询规划"
        description="所有问题先形成结构化问题画像，再由规划器在记忆、契约、热点工件和按需计算之间选路。更新语义已经并入本页，作为选路依据的一部分。"
      />

      <div className="flex flex-wrap gap-2">
        {[
          { key: 'planner', label: '查询规划' },
          { key: 'update-semantics', label: '更新语义' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => switchTab(tab.key as PlannerTab)}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
              activeTab === tab.key
                ? 'border-[var(--df-ink)] bg-[var(--df-ink)] text-white'
                : 'border-[var(--df-border)] bg-[var(--df-surface)] text-[var(--df-text-muted)] hover:bg-[var(--df-surface-2)]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'update-semantics' ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <FabricStatCard label="识别出的源" value={updateResponse?.total ?? 0} />
            <FabricStatCard label="增量倾向" value={updateItems.filter((item) => ['UPSERT', 'APPEND'].includes(item.update_mode)).length} hint="更适合热点工件和高频路径" />
            <FabricStatCard label="全量倾向" value={updateItems.filter((item) => ['FULL_SNAPSHOT', 'PERIODIC_FULL'].includes(item.update_mode)).length} hint="更适合记忆摘要和按需计算" />
            <FabricStatCard label="高置信判断" value={updateItems.filter((item) => item.confidence >= 0.8).length} />
          </div>

          <FabricSection title="更新语义列表" subtitle="平台根据主键、时间字段、刷新节奏和历史扫描结果判断数据如何变化，并把这个判断作为 Planner 选路依据。">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
              <FabricSearchInput
                value={updateQuery}
                placeholder="搜索源名称、模式或判断原因"
                onChange={(value) => {
                  setUpdateQuery(value)
                  setUpdateOffset(0)
                }}
              />
              <FabricFilterSelect
                value={updateMode}
                onChange={(value) => {
                  setUpdateMode(value)
                  setUpdateOffset(0)
                }}
                options={updateModes}
              />
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">Memory Path：优先使用更新稳定、刷新低频、适合摘要和知识检索的源。</div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">Contract Path：优先使用已确认契约和稳定口径，避免直接扫原始明细。</div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">Hot Artifact Path：优先服务高热、增量明显、复用度高的热点结果。</div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">On-demand Compute Path：用于全量快照、重型分析和首次复杂问题。</div>
            </div>

            <div className="mt-5 space-y-3">
              {loadingUpdates ? (
                <FabricEmptyState message="正在加载更新语义..." />
              ) : updateItems.length === 0 ? (
                <FabricEmptyState message="当前筛选条件下没有更新语义结果。" />
              ) : (
                updateItems.map((item) => (
                  <div key={item.source_id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="inline-flex items-center gap-2 font-semibold text-slate-900">
                            <Workflow size={16} />
                            {item.source_name}
                          </div>
                          <FabricBadge value={item.source_type} />
                          <FabricBadge value={item.update_mode} />
                          <FabricBadge value={item.planner_strategy} />
                        </div>
                        <div className="mt-2 text-sm text-slate-600">
                          刷新节奏 {item.refresh_cadence}，置信度 {(item.confidence * 100).toFixed(0)}%，最近扫描 {formatDateTime(item.last_scanned_at)}
                        </div>
                        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                          {item.reasoning.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="min-w-[280px] rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="text-sm font-medium text-slate-900">推荐动作</div>
                        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600">
                          {item.recommended_actions.map((action) => (
                            <li key={action}>{action}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
                      {item.key_candidates.map((candidate) => (
                        <span key={candidate} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
                          主键候选：{candidate}
                        </span>
                      ))}
                      {item.time_candidates.map((candidate) => (
                        <span key={candidate} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
                          时间字段：{candidate}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
              {updateResponse ? (
                <FabricPager total={updateResponse.total} limit={updateResponse.limit} offset={updateResponse.offset} onChange={setUpdateOffset} />
              ) : null}
            </div>
          </FabricSection>
        </>
      ) : (
        <>
          <FabricSection title="规划输入" subtitle="先用自然语言描述业务问题，再由平台生成问题画像、推荐路径和预备 SQL。重型问题只返回异步计划，不在本页直接执行。">
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {STARTER_QUESTIONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setQuestion(item)}
                    className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                  >
                    {item}
                  </button>
                ))}
              </div>

              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={4}
                placeholder="例如：请规划围绕订单主题域的高频查询路径，并说明是否应该优先命中热点工件。"
                className="w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none"
              />

              <div className="flex flex-wrap items-center gap-3">
                <label className="text-sm text-slate-600">延迟目标</label>
                <select
                  value={latencyTarget}
                  onChange={(event) => setLatencyTarget(Number(event.target.value))}
                  className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
                >
                  {[200, 500, 800, 1500, 3000].map((value) => (
                    <option key={value} value={value}>
                      {value}ms
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void submitPlan()}
                  className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
                >
                  <Send size={15} />
                  {loadingSubmit ? '规划中...' : '生成规划'}
                </button>
              </div>
            </div>
          </FabricSection>

          {submission ? (
            <>
              <div className="grid gap-4 md:grid-cols-4">
                <FabricStatCard label="问题类型" value={submission.intent.intent_type} />
                <FabricStatCard label="已选路径" value={submission.plan.selected_path} />
                <FabricStatCard label="执行模式" value={submission.run.execution_mode} />
                <FabricStatCard label="当前状态" value={submission.run.status} />
              </div>

              <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
                <FabricSection title="问题画像" subtitle="规划器先抽取主题域、时间范围、指标和维度，再决定应该走哪条路径。">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">主题域</div>
                      <div className="mt-2 font-semibold text-slate-900">{submission.intent.domain || '通用主题'}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">时间范围</div>
                      <div className="mt-2 font-semibold text-slate-900">{submission.intent.time_scope || '未显式指定'}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">指标</div>
                      <div className="mt-2 text-sm text-slate-700">{joinList(submission.intent.metrics)}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">维度</div>
                      <div className="mt-2 text-sm text-slate-700">{joinList(submission.intent.dimensions)}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 md:col-span-2">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">候选路径</div>
                      <div className="mt-2 text-sm text-slate-700">{joinList(submission.intent.candidate_paths)}</div>
                    </div>
                  </div>
                </FabricSection>

                <FabricSection title="规划摘要" subtitle="展示 trace、引擎策略和当前阶段推荐动作。">
                  <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Trace ID</div>
                      <div className="mt-2 break-all font-mono text-sm text-slate-700">{submission.trace_id}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500">执行引擎策略</div>
                      <div className="mt-2 font-semibold text-slate-900">{submission.plan.engine_strategy || '未指定'}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                      {submission.plan.rationale}
                    </div>
                  </div>
                </FabricSection>
              </div>
            </>
          ) : null}

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
            <FabricSection title="执行链详情" subtitle="查看阶段级计划、预备 SQL、命中对象和工件候选。">
              {!selectedRunDetail ? (
                <FabricEmptyState message="先生成一条规划，或从下方最近运行中选择一条。" />
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-4">
                    <FabricStatCard label="运行状态" value={selectedRunDetail.run.status} />
                    <FabricStatCard label="执行模式" value={selectedRunDetail.run.execution_mode} />
                    <FabricStatCard label="当前阶段" value={selectedRunDetail.run.current_stage || '未开始'} />
                    <FabricStatCard label="工件候选" value={selectedRunDetail.artifacts.length} />
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                    <div className="inline-flex items-center gap-2 text-sm font-medium text-slate-900">
                      <Workflow size={16} />
                      阶段计划
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {selectedRunDetail.stages.map((stage) => (
                        <div key={stage.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                          <div className="flex items-center gap-2">
                            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">阶段 {stage.stage_no}</div>
                            <FabricBadge value={stage.status} />
                          </div>
                          <div className="mt-2 font-semibold text-slate-900">{stage.title}</div>
                          <div className="mt-2 text-sm leading-6 text-slate-600">{stage.goal}</div>
                          <div className="mt-3 text-xs text-slate-500">
                            引擎：{stage.engine_key || '未指定'} / 开始：{formatDateTime(stage.started_at)}
                          </div>
                          {stage.error_message ? (
                            <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                              {stage.error_message}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                    <div className="inline-flex items-center gap-2 text-sm font-medium text-slate-900">
                      <FileSearch size={16} />
                      预备 SQL
                    </div>
                    <div className="mt-4 space-y-3">
                      {selectedRunDetail.prepared_sql.length === 0 ? (
                        <FabricEmptyState message="当前路径没有生成预备 SQL。" />
                      ) : (
                        selectedRunDetail.prepared_sql.map((item) => (
                          <div key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                            <div className="flex flex-wrap items-center gap-2">
                              <FabricBadge value={item.status} />
                              <FabricBadge value={item.engine_key} />
                              <span className="text-xs text-slate-500">角色：{item.execution_role}</span>
                            </div>
                            <pre className="mt-3 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
                              {item.sql_text}
                            </pre>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}
            </FabricSection>

            <div className="space-y-6">
              <FabricSection title="命中对象" subtitle="展示本次规划命中的数据源、记忆和契约。">
                {!selectedRunDetail ? (
                  <FabricEmptyState message="生成规划后，这里会出现命中对象。" />
                ) : (
                  <div className="space-y-4">
                    <div>
                      <div className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-slate-900">
                        <Bot size={16} />
                        命中数据源
                      </div>
                      <div className="space-y-2">
                        {matchedSources.length === 0 ? (
                          <div className="text-sm text-slate-500">没有命中数据源。</div>
                        ) : (
                          matchedSources.map((item, index) => (
                            <div key={`${item.source_name}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
                              {item.source_name || '未命名源'} / {item.source_type || 'UNKNOWN'} / 热度 {item.heat_level || '-'}
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-sm font-medium text-slate-900">命中记忆</div>
                      <div className="space-y-2">
                        {matchedMemories.length === 0 ? (
                          <div className="text-sm text-slate-500">没有命中记忆。</div>
                        ) : (
                          matchedMemories.map((item, index) => (
                            <div key={`${item.title}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
                              {item.title || '未命名记忆'} / {item.module || 'UNKNOWN'} / {item.status || 'UNKNOWN'}
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-sm font-medium text-slate-900">命中契约</div>
                      <div className="space-y-2">
                        {matchedContracts.length === 0 ? (
                          <div className="text-sm text-slate-500">没有命中契约。</div>
                        ) : (
                          matchedContracts.map((item, index) => (
                            <div key={`${item.contract_name}-${index}`} className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
                              {item.contract_name || '未命名契约'} / {item.event_code || 'NO_CODE'} / {item.serving_status || 'UNKNOWN'}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </FabricSection>

              <FabricSection title="最近规划运行" subtitle="所有问题都会保留规划记录，支持筛选和分页。">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
                  <FabricSearchInput
                    value={query}
                    placeholder="搜索问题、主题域或 trace"
                    onChange={(value) => {
                      setQuery(value)
                      setOffset(0)
                    }}
                  />
                  <div className="grid gap-3 md:grid-cols-3">
                    <FabricFilterSelect
                      value={status}
                      onChange={(value) => {
                        setStatus(value)
                        setOffset(0)
                      }}
                      options={[
                        { label: '全部状态', value: 'ALL' },
                        { label: 'WAITING_CONFIRMATION', value: 'WAITING_CONFIRMATION' },
                        { label: 'COMPLETED', value: 'COMPLETED' },
                        { label: 'FAILED', value: 'FAILED' },
                      ]}
                    />
                    <FabricFilterSelect
                      value={intentType}
                      onChange={(value) => {
                        setIntentType(value)
                        setOffset(0)
                      }}
                      options={[
                        { label: '全部类型', value: 'ALL' },
                        { label: '记忆类', value: 'MEMORY' },
                        { label: '状态类', value: 'STATUS' },
                        { label: '契约类', value: 'CONTRACT' },
                        { label: '热点分析类', value: 'HOT_ANALYTICS' },
                        { label: '即席分析类', value: 'AD_HOC_ANALYTICS' },
                        { label: '治理操作类', value: 'GOVERNANCE_ACTION' },
                      ]}
                    />
                    <FabricFilterSelect
                      value={selectedPath}
                      onChange={(value) => {
                        setSelectedPath(value)
                        setOffset(0)
                      }}
                      options={[
                        { label: '全部路径', value: 'ALL' },
                        { label: 'MEMORY_ONLY', value: 'MEMORY_ONLY' },
                        { label: 'CONTRACT_FIRST', value: 'CONTRACT_FIRST' },
                        { label: 'HOT_MATERIALIZATION', value: 'HOT_MATERIALIZATION' },
                        { label: 'ON_DEMAND_COMPUTE', value: 'ON_DEMAND_COMPUTE' },
                      ]}
                    />
                  </div>
                </div>

                <div className="mt-5 space-y-3">
                  {loadingRuns ? (
                    <FabricEmptyState message="正在加载规划运行..." />
                  ) : (runs?.items.length ?? 0) === 0 ? (
                    <FabricEmptyState message="当前筛选条件下没有规划记录。" />
                  ) : (
                    (runs?.items ?? []).map((run) => (
                      <button
                        key={run.id}
                        type="button"
                        onClick={() => void loadRunDetail(run.id)}
                        className={`w-full rounded-2xl border p-4 text-left transition ${
                          selectedRunDetail?.run.id === run.id
                            ? 'border-slate-900 bg-slate-900 text-white'
                            : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white'
                        }`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="truncate text-base font-semibold">{run.question}</div>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${selectedRunDetail?.run.id === run.id ? 'border-white/20 bg-white/10 text-white' : 'border-slate-200 bg-white text-slate-700'}`}>
                            {run.intent_type}
                          </span>
                          <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${selectedRunDetail?.run.id === run.id ? 'border-white/20 bg-white/10 text-white' : 'border-slate-200 bg-white text-slate-700'}`}>
                            {run.selected_path}
                          </span>
                        </div>
                        <div className={`mt-2 text-sm ${selectedRunDetail?.run.id === run.id ? 'text-slate-200' : 'text-slate-600'}`}>
                          主题域：{run.domain || '通用主题'} / 状态：{run.status} / 提交时间：{formatDateTime(run.submitted_at || run.created_at)}
                        </div>
                      </button>
                    ))
                  )}
                  {runs ? <FabricPager total={runs.total} limit={runs.limit} offset={runs.offset} onChange={setOffset} /> : null}
                </div>
              </FabricSection>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

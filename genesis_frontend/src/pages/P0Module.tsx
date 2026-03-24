import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { BrainCircuit, Eye, FileCheck2, Network, Search, ShieldCheck, X } from 'lucide-react'

import {
  GenesisApi,
  type P0ContractArtifact,
  type P0EntityListResponse,
  type P0GovernanceRecord,
  type P0InferenceCandidate,
  type P0ObjectDetailState,
  type P0OverviewResponse,
  type P0SourceProfile,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const PAGE_SIZE = 8

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: number | string
  icon: any
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.14em] text-slate-500">{label}</div>
          <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{value}</div>
        </div>
        <div className="rounded-2xl bg-slate-100 p-3 text-slate-700">
          <Icon size={20} />
        </div>
      </div>
    </div>
  )
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{title}</h3>
        <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
      </div>
      {children}
    </section>
  )
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
}) {
  return (
    <div className="relative">
      <Search size={15} className="absolute left-3 top-3 text-slate-400" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-10 py-2.5 text-sm text-slate-700 outline-none placeholder:text-slate-400"
      />
    </div>
  )
}

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (value: string) => void
  options: Array<{ label: string; value: string }>
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  const currentPage = total === 0 ? 1 : Math.floor(offset / limit) + 1
  const totalPages = Math.max(Math.ceil(total / limit), 1)

  return (
    <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
      <div>{total === 0 ? '0' : `${offset + 1}-${Math.min(offset + limit, total)}`} / {total}</div>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={offset <= 0}
          onClick={() => onChange(Math.max(offset - limit, 0))}
          className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          上一页
        </button>
        <div className="rounded-xl bg-slate-50 px-3 py-1.5">
          {currentPage}/{totalPages}
        </div>
        <button
          type="button"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
          className="rounded-xl border border-slate-200 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          下一页
        </button>
      </div>
    </div>
  )
}

function DetailModal({
  selectedObject,
  selectedDetail,
  onClose,
}: {
  selectedObject: P0ObjectDetailState | null
  selectedDetail: unknown
  onClose: () => void
}) {
  if (!selectedObject) return null

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/40 p-6">
      <div className="w-full max-w-3xl rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
              {selectedObject.object_type}
            </div>
            <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
              对象详情 #{selectedObject.object_id}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-200 bg-slate-50 p-2 text-slate-500 hover:bg-slate-100"
          >
            <X size={16} />
          </button>
        </div>
        <div className="mt-5">
          {!selectedDetail ? (
            <div className="text-sm text-slate-500">正在加载详情...</div>
          ) : (
            <pre className="max-h-[65vh] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
              {JSON.stringify(selectedDetail, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

function ItemCard({
  title,
  subtitle,
  meta,
  onClick,
}: {
  title: string
  subtitle?: string
  meta?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-slate-300 hover:bg-white"
    >
      <div className="font-semibold text-slate-900">{title}</div>
      {subtitle ? <div className="mt-1 text-sm text-slate-600">{subtitle}</div> : null}
      {meta ? <div className="mt-2 text-xs text-slate-500">{meta}</div> : null}
    </button>
  )
}

export default function P0Module() {
  const { locale } = useLanguage()
  void locale

  const [overview, setOverview] = useState<P0OverviewResponse | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)

  const [sourceQuery, setSourceQuery] = useState('')
  const [sourceHeat, setSourceHeat] = useState('ALL')
  const [sourceOffset, setSourceOffset] = useState(0)
  const [sourceProfiles, setSourceProfiles] = useState<P0EntityListResponse<P0SourceProfile> | null>(null)

  const [inferenceQuery, setInferenceQuery] = useState('')
  const [inferenceType, setInferenceType] = useState('ALL')
  const [inferenceStatus, setInferenceStatus] = useState('ALL')
  const [inferenceOffset, setInferenceOffset] = useState(0)
  const [inferenceCandidates, setInferenceCandidates] = useState<P0EntityListResponse<P0InferenceCandidate> | null>(null)

  const [governanceQuery, setGovernanceQuery] = useState('')
  const [governanceQueueStatus, setGovernanceQueueStatus] = useState('ALL')
  const [governanceDecisionStatus, setGovernanceDecisionStatus] = useState('ALL')
  const [governanceOffset, setGovernanceOffset] = useState(0)
  const [governanceRecords, setGovernanceRecords] = useState<P0EntityListResponse<P0GovernanceRecord> | null>(null)

  const [contractQuery, setContractQuery] = useState('')
  const [contractStatus, setContractStatus] = useState('ALL')
  const [contractOffset, setContractOffset] = useState(0)
  const [contractArtifacts, setContractArtifacts] = useState<P0EntityListResponse<P0ContractArtifact> | null>(null)

  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)

  useEffect(() => {
    const loadOverview = async () => {
      setLoadingOverview(true)
      try {
        setOverview(await GenesisApi.getP0Overview())
      } finally {
        setLoadingOverview(false)
      }
    }
    void loadOverview()
  }, [])

  useEffect(() => {
    void GenesisApi.getP0SourceProfiles({
      limit: PAGE_SIZE,
      offset: sourceOffset,
      heat: sourceHeat === 'ALL' ? undefined : sourceHeat,
      q: sourceQuery.trim() || undefined,
    }).then(setSourceProfiles)
  }, [sourceOffset, sourceHeat, sourceQuery])

  useEffect(() => {
    void GenesisApi.getP0InferenceCandidates({
      limit: PAGE_SIZE,
      offset: inferenceOffset,
      candidate_type: inferenceType === 'ALL' ? undefined : inferenceType,
      status: inferenceStatus === 'ALL' ? undefined : inferenceStatus,
      q: inferenceQuery.trim() || undefined,
    }).then(setInferenceCandidates)
  }, [inferenceOffset, inferenceType, inferenceStatus, inferenceQuery])

  useEffect(() => {
    void GenesisApi.getP0GovernanceRecords({
      limit: PAGE_SIZE,
      offset: governanceOffset,
      queue_status: governanceQueueStatus === 'ALL' ? undefined : governanceQueueStatus,
      decision_status:
        governanceDecisionStatus === 'ALL' ? undefined : governanceDecisionStatus,
      q: governanceQuery.trim() || undefined,
    }).then(setGovernanceRecords)
  }, [governanceOffset, governanceQueueStatus, governanceDecisionStatus, governanceQuery])

  useEffect(() => {
    void GenesisApi.getP0ContractArtifacts({
      limit: PAGE_SIZE,
      offset: contractOffset,
      serving_status: contractStatus === 'ALL' ? undefined : contractStatus,
      q: contractQuery.trim() || undefined,
    }).then(setContractArtifacts)
  }, [contractOffset, contractStatus, contractQuery])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }

    const loadDetail = async () => {
      if (selectedObject.object_type === 'SOURCE_PROFILE') {
        setSelectedDetail(await GenesisApi.getP0SourceProfileDetail(selectedObject.object_id))
      } else if (selectedObject.object_type === 'INFERENCE_CANDIDATE') {
        setSelectedDetail(
          await GenesisApi.getP0InferenceCandidateDetail(selectedObject.object_id),
        )
      } else if (selectedObject.object_type === 'GOVERNANCE_RECORD') {
        setSelectedDetail(await GenesisApi.getP0GovernanceRecordDetail(selectedObject.object_id))
      } else {
        setSelectedDetail(await GenesisApi.getP0ContractArtifactDetail(selectedObject.object_id))
      }
    }

    void loadDetail()
  }, [selectedObject])

  const observationStats = useMemo(
    () => [
      { label: '总日志量', value: overview?.observation.total_logs ?? '-', icon: Eye },
      { label: '近 7 天事件', value: overview?.observation.events_7d ?? '-', icon: Network },
      {
        label: '活跃通道',
        value: overview?.observation.active_channels ?? '-',
        icon: Network,
      },
    ],
    [overview],
  )

  if (loadingOverview || !overview) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">
        正在加载 P0 模块...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">P0 模块</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
          P0 单页工作台
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          将 Observation、Inference、Governance 和 Contract 统一展示在一个页面中，支持搜索、筛选、分页和弹窗查看详情。
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="观察源" value={overview.summary.observation_sources} icon={Network} />
        <StatCard label="已观察事件" value={overview.summary.observed_events} icon={Eye} />
        <StatCard label="推断队列" value={overview.summary.inference_queue} icon={BrainCircuit} />
        <StatCard label="已发布契约" value={overview.summary.published_contracts} icon={FileCheck2} />
      </div>

      <Section title="Observation" subtitle="查看原始信号、源画像和冷热分布。">
        <div className="grid gap-4 md:grid-cols-3">
          {observationStats.map((item) => (
            <StatCard key={item.label} label={item.label} value={item.value} icon={item.icon} />
          ))}
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
          <SearchBox
            value={sourceQuery}
            onChange={(value) => {
              setSourceQuery(value)
              setSourceOffset(0)
            }}
            placeholder="搜索源画像或事件名称"
          />
          <FilterSelect
            value={sourceHeat}
            onChange={(value) => {
              setSourceHeat(value)
              setSourceOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部冷热' },
              { value: 'HOT', label: 'HOT' },
              { value: 'WARM', label: 'WARM' },
              { value: 'COLD', label: 'COLD' },
            ]}
          />
        </div>

        <div className="mt-5 grid gap-3 xl:grid-cols-2">
          {(sourceProfiles?.items ?? []).map((item) => (
            <ItemCard
              key={`${item.channel_id}:${item.event_name}`}
              title={item.event_name}
              subtitle={`通道：${item.channel_id}｜冷热：${item.heat}`}
              meta={`总事件数：${item.total_events}｜通过事件：${item.accepted_events}`}
              onClick={() =>
                setSelectedObject({
                  object_type: 'SOURCE_PROFILE',
                  object_id: item.id ?? item.channel_id,
                })
              }
            />
          ))}
        </div>

        {sourceProfiles ? (
          <Pager
            total={sourceProfiles.total}
            limit={sourceProfiles.limit ?? PAGE_SIZE}
            offset={sourceProfiles.offset ?? 0}
            onChange={setSourceOffset}
          />
        ) : null}
      </Section>

      <Section title="Inference" subtitle="查看推断产生的语义候选和结构候选。">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          <StatCard label="候选总数" value={overview.inference.total_proposals} icon={BrainCircuit} />
          <StatCard label="待处理" value={overview.inference.pending_proposals} icon={BrainCircuit} />
          <StatCard
            label="高置信候选"
            value={overview.inference.high_confidence_pending}
            icon={BrainCircuit}
          />
          <StatCard label="AI 生成" value={overview.inference.ai_generated_pending} icon={BrainCircuit} />
          <StatCard label="未映射信号" value={overview.inference.unmapped_pending} icon={BrainCircuit} />
          <StatCard label="平均置信度" value={overview.inference.avg_confidence} icon={BrainCircuit} />
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
          <SearchBox
            value={inferenceQuery}
            onChange={(value) => {
              setInferenceQuery(value)
              setInferenceOffset(0)
            }}
            placeholder="搜索目标字段、路径或推断理由"
          />
          <FilterSelect
            value={inferenceType}
            onChange={(value) => {
              setInferenceType(value)
              setInferenceOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部类型' },
              { value: 'SEMANTIC_MAPPING', label: 'SEMANTIC_MAPPING' },
              { value: 'UNMAPPED_SIGNAL', label: 'UNMAPPED_SIGNAL' },
            ]}
          />
          <FilterSelect
            value={inferenceStatus}
            onChange={(value) => {
              setInferenceStatus(value)
              setInferenceOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部状态' },
              { value: 'PENDING', label: 'PENDING' },
              { value: 'APPROVED', label: 'APPROVED' },
              { value: 'REJECTED', label: 'REJECTED' },
            ]}
          />
        </div>

        <div className="mt-5 space-y-3">
          {(inferenceCandidates?.items ?? []).map((item) => (
            <ItemCard
              key={item.id}
              title={`${item.target_field}｜${item.candidate_type}`}
              subtitle={item.reasoning ?? item.recommended_action}
              meta={`置信度：${item.confidence_score}｜状态：${item.status}`}
              onClick={() =>
                setSelectedObject({ object_type: 'INFERENCE_CANDIDATE', object_id: item.id })
              }
            />
          ))}
        </div>

        {inferenceCandidates ? (
          <Pager
            total={inferenceCandidates.total}
            limit={inferenceCandidates.limit ?? PAGE_SIZE}
            offset={inferenceCandidates.offset ?? 0}
            onChange={setInferenceOffset}
          />
        ) : null}
      </Section>

      <Section title="Governance" subtitle="跟踪审核队列和治理决策。">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
          <StatCard label="待审核" value={overview.governance.pending_reviews} icon={ShieldCheck} />
          <StatCard label="已批准" value={overview.governance.approved_rules} icon={ShieldCheck} />
          <StatCard label="已拒绝" value={overview.governance.rejected_rules} icon={ShieldCheck} />
          <StatCard label="开放队列" value={overview.governance.queue.length} icon={ShieldCheck} />
          <StatCard
            label="近期决策"
            value={overview.governance.recent_decisions.length}
            icon={ShieldCheck}
          />
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
          <SearchBox
            value={governanceQuery}
            onChange={(value) => {
              setGovernanceQuery(value)
              setGovernanceOffset(0)
            }}
            placeholder="搜索字段、备注或处理人"
          />
          <FilterSelect
            value={governanceQueueStatus}
            onChange={(value) => {
              setGovernanceQueueStatus(value)
              setGovernanceOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部队列' },
              { value: 'OPEN', label: 'OPEN' },
              { value: 'CLOSED', label: 'CLOSED' },
            ]}
          />
          <FilterSelect
            value={governanceDecisionStatus}
            onChange={(value) => {
              setGovernanceDecisionStatus(value)
              setGovernanceOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部决策' },
              { value: 'APPROVED', label: 'APPROVED' },
              { value: 'REJECTED', label: 'REJECTED' },
              { value: 'PENDING', label: 'PENDING' },
            ]}
          />
        </div>

        <div className="mt-5 space-y-3">
          {(governanceRecords?.items ?? []).map((item) => (
            <ItemCard
              key={item.id}
              title={`${item.target_field}｜${item.decision_status}`}
              subtitle={`队列：${item.queue_status}｜建议动作：${item.recommended_action}`}
              meta={`置信度：${item.confidence_score}${item.actor ? `｜处理人：${item.actor}` : ''}`}
              onClick={() =>
                setSelectedObject({ object_type: 'GOVERNANCE_RECORD', object_id: item.id })
              }
            />
          ))}
        </div>

        {governanceRecords ? (
          <Pager
            total={governanceRecords.total}
            limit={governanceRecords.limit ?? PAGE_SIZE}
            offset={governanceRecords.offset ?? 0}
            onChange={setGovernanceOffset}
          />
        ) : null}
      </Section>

      <Section title="Contract" subtitle="查看最终发布的契约和服务工件。">
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard label="有效契约" value={overview.contract.active_contracts} icon={FileCheck2} />
          <StatCard label="已批准规则" value={overview.contract.approved_rules} icon={FileCheck2} />
          <StatCard label="已发布工件" value={overview.contract.artifacts.length} icon={FileCheck2} />
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
          <SearchBox
            value={contractQuery}
            onChange={(value) => {
              setContractQuery(value)
              setContractOffset(0)
            }}
            placeholder="搜索契约名称或事件编码"
          />
          <FilterSelect
            value={contractStatus}
            onChange={(value) => {
              setContractStatus(value)
              setContractOffset(0)
            }}
            options={[
              { value: 'ALL', label: '全部服务状态' },
              { value: 'PUBLISHED', label: 'PUBLISHED' },
              { value: 'DRAFT', label: 'DRAFT' },
              { value: 'ARCHIVED', label: 'ARCHIVED' },
            ]}
          />
        </div>

        <div className="mt-5 space-y-3">
          {(contractArtifacts?.items ?? []).map((item) => (
            <ItemCard
              key={`${item.event_id}:${item.contract_name}`}
              title={item.contract_name}
              subtitle={`事件：${item.event_code}`}
              meta={`已批准规则：${item.approved_rule_count}｜状态：${item.serving_status}`}
              onClick={() =>
                setSelectedObject({
                  object_type: 'CONTRACT_ARTIFACT',
                  object_id: item.id ?? item.event_id,
                })
              }
            />
          ))}
        </div>

        {contractArtifacts ? (
          <Pager
            total={contractArtifacts.total}
            limit={contractArtifacts.limit ?? PAGE_SIZE}
            offset={contractArtifacts.offset ?? 0}
            onChange={setContractOffset}
          />
        ) : null}
      </Section>

      <DetailModal
        selectedObject={selectedObject}
        selectedDetail={selectedDetail}
        onClose={() => setSelectedObject(null)}
      />
    </div>
  )
}

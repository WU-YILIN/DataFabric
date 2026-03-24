import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BrainCircuit,
  Eye,
  FileCheck2,
  Network,
  ShieldCheck,
} from 'lucide-react'

import {
  GenesisApi,
  type P0ContractArtifact,
  type P0GovernanceRecord,
  type P0InferenceCandidate,
  type P0ObjectDetailState,
  type P0OverviewResponse,
  type P0SourceProfile,
} from '../services/api'
import { useLanguage } from '../i18n/language'

function MetricCard({
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

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: React.ReactNode
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

function FilterPills({
  options,
  value,
  onChange,
}: {
  options: Array<{ label: string; value: string }>
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`rounded-full px-3 py-1 text-xs font-medium transition ${
            value === option.value
              ? 'bg-slate-900 text-white'
              : 'border border-slate-200 bg-slate-50 text-slate-600 hover:bg-white'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function ClickableItem({
  onClick,
  children,
}: {
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-2xl bg-slate-50 px-4 py-3 text-left text-sm transition hover:bg-slate-100"
    >
      {children}
    </button>
  )
}

export default function P0ControlPlane() {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [data, setData] = useState<P0OverviewResponse | null>(null)
  const [sourceProfiles, setSourceProfiles] = useState<P0SourceProfile[]>([])
  const [inferenceCandidates, setInferenceCandidates] = useState<P0InferenceCandidate[]>([])
  const [governanceRecords, setGovernanceRecords] = useState<P0GovernanceRecord[]>([])
  const [contractArtifacts, setContractArtifacts] = useState<P0ContractArtifact[]>([])
  const [sourceHeat, setSourceHeat] = useState('ALL')
  const [candidateType, setCandidateType] = useState('ALL')
  const [governanceQueueStatus, setGovernanceQueueStatus] = useState('ALL')
  const [contractStatus, setContractStatus] = useState('ALL')
  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      GenesisApi.getP0Overview(),
      GenesisApi.getP0SourceProfiles({ limit: 12, heat: sourceHeat === 'ALL' ? undefined : sourceHeat }),
      GenesisApi.getP0InferenceCandidates({
        limit: 12,
        candidate_type: candidateType === 'ALL' ? undefined : candidateType,
      }),
      GenesisApi.getP0GovernanceRecords({
        limit: 16,
        queue_status: governanceQueueStatus === 'ALL' ? undefined : governanceQueueStatus,
      }),
      GenesisApi.getP0ContractArtifacts({
        limit: 12,
        serving_status: contractStatus === 'ALL' ? undefined : contractStatus,
      }),
    ])
      .then(([overview, sourceProfileResponse, inferenceResponse, governanceResponse, contractResponse]) => {
        setData(overview)
        setSourceProfiles(sourceProfileResponse.items)
        setInferenceCandidates(inferenceResponse.items)
        setGovernanceRecords(governanceResponse.items)
        setContractArtifacts(contractResponse.items)
      })
      .catch((err: any) => {
        setError(err?.response?.data?.message ?? L('加载 P0 控制面失败', 'Failed to load P0 control plane'))
      })
  }, [candidateType, contractStatus, governanceQueueStatus, sourceHeat])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }

    let cancelled = false
    const loadDetail = async () => {
      try {
        let detail: unknown
        if (selectedObject.object_type === 'SOURCE_PROFILE') {
          detail = await GenesisApi.getP0SourceProfileDetail(selectedObject.object_id)
        } else if (selectedObject.object_type === 'INFERENCE_CANDIDATE') {
          detail = await GenesisApi.getP0InferenceCandidateDetail(selectedObject.object_id)
        } else if (selectedObject.object_type === 'GOVERNANCE_RECORD') {
          detail = await GenesisApi.getP0GovernanceRecordDetail(selectedObject.object_id)
        } else {
          detail = await GenesisApi.getP0ContractArtifactDetail(selectedObject.object_id)
        }
        if (!cancelled) {
          setSelectedDetail(detail)
        }
      } catch {
        if (!cancelled) {
          setSelectedDetail(null)
        }
      }
    }

    void loadDetail()
    return () => {
      cancelled = true
    }
  }, [selectedObject])

  if (!data) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="text-sm text-slate-500">{error ?? L('正在加载 P0 控制面...', 'Loading P0 control plane...')}</div>
      </div>
    )
  }

  const openGovernanceRecords = governanceRecords.filter((item) => item.queue_status === 'OPEN')
  const closedGovernanceRecords = governanceRecords.filter((item) => item.queue_status !== 'OPEN')

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">DataFabric P0</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{L('从 Observation 到 Contract 的控制面', 'Observation to Contract control plane')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {L('P0 只关注一条闭环：观察原始输入、推断候选语义、治理高风险变更，并为消费方发布稳定契约。', 'P0 focuses on one closed loop only: observe raw inputs, infer candidate meaning, govern high-risk changes, and publish stable contracts for consumers.')}
        </p>
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Link
            to="/events"
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-white"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-900">{L('Observation', 'Observation')}</span>
              <ArrowRight size={16} />
            </div>
            <div className="mt-1 text-xs text-slate-500">{L('查看原始变化和源信号', 'Inspect raw changes and source signals')}</div>
          </Link>
          <Link
            to="/schema-mapping"
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-white"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-900">{L('Inference', 'Inference')}</span>
              <ArrowRight size={16} />
            </div>
            <div className="mt-1 text-xs text-slate-500">{L('审阅候选判断和置信度', 'Review candidate judgments and confidence')}</div>
          </Link>
          <Link
            to="/governance"
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-white"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-900">{L('Governance', 'Governance')}</span>
              <ArrowRight size={16} />
            </div>
            <div className="mt-1 text-xs text-slate-500">{L('批准、拒绝并审计高风险变更', 'Approve, reject, and audit high-risk changes')}</div>
          </Link>
          <Link
            to="/explore"
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition hover:border-slate-300 hover:bg-white"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-900">{L('Contract', 'Contract')}</span>
              <ArrowRight size={16} />
            </div>
            <div className="mt-1 text-xs text-slate-500">{L('消费治理后的稳定输出', 'Consume stable outputs after governance')}</div>
          </Link>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Observation Sources"
          value={data.summary.observation_sources}
          icon={Network}
        />
        <MetricCard label="Observed Events" value={data.summary.observed_events} icon={Eye} />
        <MetricCard
          label="Inference Queue"
          value={data.summary.inference_queue}
          icon={BrainCircuit}
        />
        <MetricCard
          label="Published Contracts"
          value={data.summary.published_contracts}
          icon={FileCheck2}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard
          title="Observation"
          subtitle="What the platform has already seen from raw sources."
        >
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <MetricCard label="Total Logs" value={data.observation.total_logs} icon={Eye} />
            <MetricCard label="Events 7d" value={data.observation.events_7d} icon={Network} />
            <MetricCard
              label="Active Channels"
              value={data.observation.active_channels}
              icon={ShieldCheck}
            />
          </div>
          <div className="space-y-2">
            {data.observation.top_sources.map((item) => (
              <div
                key={item.event_name}
                className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-sm"
              >
                <span className="font-medium text-slate-900">{item.event_name}</span>
                <span className="text-slate-500">{item.event_count}</span>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Inference"
          subtitle="Candidate judgments generated from observed source patterns."
        >
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <MetricCard
              label="Pending"
              value={data.inference.pending_proposals}
              icon={BrainCircuit}
            />
            <MetricCard
              label="High Confidence"
              value={data.inference.high_confidence_pending}
              icon={ShieldCheck}
            />
            <MetricCard
              label="Avg Confidence"
              value={`${Math.round(data.inference.avg_confidence * 100)}%`}
              icon={FileCheck2}
            />
          </div>
          <div className="mb-4 grid gap-3 md:grid-cols-2">
            <MetricCard
              label="AI Generated Pending"
              value={data.inference.ai_generated_pending}
              icon={BrainCircuit}
            />
            <MetricCard
              label="Unmapped Pending"
              value={data.inference.unmapped_pending}
              icon={Eye}
            />
          </div>
          <div className="space-y-2">
            {data.inference.top_proposals.map((item) => (
              <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{Math.round(item.confidence_score * 100)}%</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Event {item.event_id} | {item.source_paths.join(', ')}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.proposed_by} | {item.recommended_action}
                </div>
                {item.ai_reasoning && (
                  <div className="mt-2 text-xs text-slate-600">{item.ai_reasoning}</div>
                )}
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Governance"
          subtitle="Human gate for high-risk changes before anything becomes official."
        >
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <MetricCard
              label="Pending Reviews"
              value={data.governance.pending_reviews}
              icon={ShieldCheck}
            />
            <MetricCard
              label="Approved Rules"
              value={data.governance.approved_rules}
              icon={FileCheck2}
            />
            <MetricCard
              label="Rejected Rules"
              value={data.governance.rejected_rules}
              icon={BrainCircuit}
            />
          </div>
          <div className="space-y-2">
            {closedGovernanceRecords.slice(0, 8).map((item) => (
              <ClickableItem
                key={item.id}
                onClick={() =>
                  setSelectedObject({ object_type: 'GOVERNANCE_RECORD', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.decision_status}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Event {item.event_id} | {item.actor ?? 'system'}
                </div>
              </ClickableItem>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Contract"
          subtitle="Stable serving artifacts published after governance approval."
        >
          <div className="mb-4 grid gap-3 md:grid-cols-2">
            <MetricCard
              label="Active Contracts"
              value={data.contract.active_contracts}
              icon={FileCheck2}
            />
            <MetricCard
              label="Approved Rules"
              value={data.contract.approved_rules}
              icon={ShieldCheck}
            />
          </div>
          <div className="space-y-2">
            {contractArtifacts.slice(0, 8).map((item) => (
              <ClickableItem
                key={item.id ?? item.contract_name}
                onClick={() =>
                  item.id &&
                  setSelectedObject({ object_type: 'CONTRACT_ARTIFACT', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.event_code}</span>
                  <span className="text-slate-500">{item.serving_status}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.contract_name} | {item.approved_rule_count} approved rules
                </div>
              </ClickableItem>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard
          title="Inference Candidates"
          subtitle="Normalized candidate judgments before they become governed rules."
        >
          <FilterPills
            value={candidateType}
            onChange={setCandidateType}
            options={[
              { label: 'All', value: 'ALL' },
              { label: 'Semantic', value: 'SEMANTIC_MAPPING' },
              { label: 'Unmapped', value: 'UNMAPPED_SIGNAL' },
            ]}
          />
          <div className="space-y-2">
            {inferenceCandidates.map((item) => (
              <ClickableItem
                key={item.id}
                onClick={() =>
                  setSelectedObject({ object_type: 'INFERENCE_CANDIDATE', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.candidate_type}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Event {item.event_id} | {Math.round(item.confidence_score * 100)}% | {item.recommended_action}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.source_paths.join(', ')}
                </div>
                {item.reasoning && (
                  <div className="mt-2 text-xs text-slate-600">{item.reasoning}</div>
                )}
              </ClickableItem>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Governance Queue"
          subtitle="The next candidate judgments waiting to become formal rules."
        >
          <FilterPills
            value={governanceQueueStatus}
            onChange={setGovernanceQueueStatus}
            options={[
              { label: 'All', value: 'ALL' },
              { label: 'Open', value: 'OPEN' },
              { label: 'Closed', value: 'CLOSED' },
            ]}
          />
          <div className="mb-4 grid gap-3 md:grid-cols-3">
            <MetricCard
              label="Pending"
              value={data.governance.decision_summary.pending}
              icon={ShieldCheck}
            />
            <MetricCard
              label="Approved"
              value={data.governance.decision_summary.approved}
              icon={FileCheck2}
            />
            <MetricCard
              label="Rejected"
              value={data.governance.decision_summary.rejected}
              icon={BrainCircuit}
            />
          </div>
          <div className="space-y-2">
            {openGovernanceRecords.map((item) => (
              <ClickableItem
                key={item.id}
                onClick={() =>
                  setSelectedObject({ object_type: 'GOVERNANCE_RECORD', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.recommended_action}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Event {item.event_id} | {Math.round(item.confidence_score * 100)}% | freq {item.field_frequency}
                </div>
              </ClickableItem>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Observation Source Profiles"
          subtitle="The strongest source fingerprints currently visible to the platform."
        >
          <FilterPills
            value={sourceHeat}
            onChange={setSourceHeat}
            options={[
              { label: 'All', value: 'ALL' },
              { label: 'Hot', value: 'HOT' },
              { label: 'Warm', value: 'WARM' },
              { label: 'Cold', value: 'COLD' },
            ]}
          />
          <div className="space-y-2">
            {sourceProfiles.map((item) => (
              <ClickableItem
                key={`${item.id ?? item.channel_id}-${item.event_name}`}
                onClick={() =>
                  item.id &&
                  setSelectedObject({ object_type: 'SOURCE_PROFILE', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.event_name}</span>
                  <span className="text-slate-500">{item.heat}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Channel {item.channel_id} | {item.accepted_events}/{item.total_events} accepted
                  {' | '}
                  {item.sdk_version ?? 'unknown sdk'}
                </div>
              </ClickableItem>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Contract Artifacts"
          subtitle="Published semantic outputs that consumers can depend on."
        >
          <FilterPills
            value={contractStatus}
            onChange={setContractStatus}
            options={[
              { label: 'All', value: 'ALL' },
              { label: 'Published', value: 'PUBLISHED' },
            ]}
          />
          <div className="space-y-2">
            {contractArtifacts.map((item) => (
              <ClickableItem
                key={item.id ?? item.contract_name}
                onClick={() =>
                  item.id &&
                  setSelectedObject({ object_type: 'CONTRACT_ARTIFACT', object_id: item.id })
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.contract_name}</span>
                  <span className="text-slate-500">{item.serving_status}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.event_code} | {item.approved_rule_count} approved rules
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.published_at ?? 'not published'}
                </div>
              </ClickableItem>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Unknown Signals"
          subtitle="High-frequency unmapped observations that should feed inference next."
        >
          <div className="space-y-2">
            {data.observation.unknown_signals.map((item) => (
              <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.field_frequency}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Event {item.event_id} | {item.source_paths.join(', ')}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Selected P0 Object"
        subtitle="Object-level detail loaded from the direct P0 endpoints."
      >
        {!selectedObject ? (
          <div className="text-sm text-slate-500">Select any P0 object card to inspect its detail.</div>
        ) : !selectedDetail ? (
          <div className="text-sm text-slate-500">Loading detail...</div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3">
              <div>
                <div className="text-xs uppercase tracking-[0.14em] text-slate-500">
                  {selectedObject.object_type}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-900">
                  object #{selectedObject.object_id}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedObject(null)
                  setSelectedDetail(null)
                }}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                Clear
              </button>
            </div>
            <pre className="overflow-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
              {JSON.stringify(selectedDetail, null, 2)}
            </pre>
          </div>
        )}
      </SectionCard>
    </div>
  )
}

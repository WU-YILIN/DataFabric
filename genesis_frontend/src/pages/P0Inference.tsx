import { useEffect, useState } from 'react'
import { BrainCircuit, FileCheck2, ShieldCheck } from 'lucide-react'

import { GenesisApi, type P0InferenceCandidate, type P0ObjectDetailState, type P0OverviewResponse } from '../services/api'
import { useLanguage } from '../i18n/language'

function Metric({ label, value, icon: Icon }: { label: string; value: number | string; icon: any }) {
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

function FilterPills({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (value: string) => void
  options: Array<{ label: string; value: string }>
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

export default function P0Inference() {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [overview, setOverview] = useState<P0OverviewResponse | null>(null)
  const [candidates, setCandidates] = useState<P0InferenceCandidate[]>([])
  const [candidateType, setCandidateType] = useState('ALL')
  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)

  useEffect(() => {
    Promise.all([
      GenesisApi.getP0Overview(),
      GenesisApi.getP0InferenceCandidates({
        limit: 20,
        candidate_type: candidateType === 'ALL' ? undefined : candidateType,
      }),
    ]).then(([overviewResponse, candidateResponse]) => {
      setOverview(overviewResponse)
      setCandidates(candidateResponse.items)
    })
  }, [candidateType])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }
    void GenesisApi.getP0InferenceCandidateDetail(selectedObject.object_id).then(setSelectedDetail)
  }, [selectedObject])

  if (!overview) {
    return <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">{L('正在加载 Inference...', 'Loading inference...')}</div>
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">P0 Inference</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{L('Inference 工作台', 'Inference workbench')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {L('在 governance 决定什么成为正式规则之前，先审阅候选判断、置信度和推理说明。', 'Review candidate judgments, confidence, and reasoning before governance decides what becomes official.')}
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        <Metric label={L('待处理', 'Pending')} value={overview.inference.pending_proposals} icon={BrainCircuit} />
        <Metric label={L('高置信', 'High Confidence')} value={overview.inference.high_confidence_pending} icon={ShieldCheck} />
        <Metric label={L('AI 生成', 'AI Generated')} value={overview.inference.ai_generated_pending} icon={BrainCircuit} />
        <Metric label={L('未映射', 'Unmapped')} value={overview.inference.unmapped_pending} icon={FileCheck2} />
        <Metric label={L('平均置信度', 'Avg Confidence')} value={`${Math.round(overview.inference.avg_confidence * 100)}%`} icon={ShieldCheck} />
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('候选对象', 'Candidate Objects')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('直接读取 P0 inference-candidate 正式对象。', 'Direct P0 inference-candidate objects.')}</p>
        <div className="mt-4">
          <FilterPills
            value={candidateType}
            onChange={setCandidateType}
            options={[
              { label: L('全部', 'All'), value: 'ALL' },
              { label: L('语义映射', 'Semantic'), value: 'SEMANTIC_MAPPING' },
              { label: L('未映射', 'Unmapped'), value: 'UNMAPPED_SIGNAL' },
            ]}
          />
          <div className="space-y-2">
            {candidates.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedObject({ object_type: 'INFERENCE_CANDIDATE', object_id: item.id })}
                className="w-full rounded-2xl bg-slate-50 px-4 py-3 text-left text-sm transition hover:bg-slate-100"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.candidate_type}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {L('事件', 'Event')} {item.event_id} | {Math.round(item.confidence_score * 100)}% | {item.recommended_action}
                </div>
                <div className="mt-1 text-xs text-slate-500">{item.source_paths.join(', ')}</div>
                {item.reasoning && <div className="mt-2 text-xs text-slate-600">{item.reasoning}</div>}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('选中候选对象', 'Selected Inference Candidate')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('详情来自 `/api/v1/p0/inference-candidates/{id}`。', 'Detail loaded from `/api/v1/p0/inference-candidates/{id}`.')}</p>
        <div className="mt-4">
          {!selectedObject ? (
            <div className="text-sm text-slate-500">{L('选择一个候选对象查看详情。', 'Select a candidate to inspect its detail.')}</div>
          ) : !selectedDetail ? (
            <div className="text-sm text-slate-500">{L('正在加载详情...', 'Loading detail...')}</div>
          ) : (
            <pre className="overflow-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
              {JSON.stringify(selectedDetail, null, 2)}
            </pre>
          )}
        </div>
      </section>
    </div>
  )
}

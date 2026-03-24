import { useEffect, useState } from 'react'
import { BrainCircuit, FileCheck2, ShieldCheck } from 'lucide-react'

import { GenesisApi, type P0GovernanceRecord, type P0ObjectDetailState, type P0OverviewResponse } from '../services/api'
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

export default function P0Governance() {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [overview, setOverview] = useState<P0OverviewResponse | null>(null)
  const [records, setRecords] = useState<P0GovernanceRecord[]>([])
  const [queueStatus, setQueueStatus] = useState('ALL')
  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)

  useEffect(() => {
    Promise.all([
      GenesisApi.getP0Overview(),
      GenesisApi.getP0GovernanceRecords({
        limit: 20,
        queue_status: queueStatus === 'ALL' ? undefined : queueStatus,
      }),
    ]).then(([overviewResponse, recordsResponse]) => {
      setOverview(overviewResponse)
      setRecords(recordsResponse.items)
    })
  }, [queueStatus])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }
    void GenesisApi.getP0GovernanceRecordDetail(selectedObject.object_id).then(setSelectedDetail)
  }, [selectedObject])

  if (!overview) {
    return <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">{L('正在加载 Governance...', 'Loading governance...')}</div>
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">P0 Governance</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{L('Governance 工作台', 'Governance workbench')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {L('在候选判断变成正式平台规则之前，审阅打开和关闭的治理记录。', 'Review open and closed governance records before candidate judgments become durable platform rules.')}
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <Metric label={L('待处理', 'Pending')} value={overview.governance.decision_summary.pending} icon={ShieldCheck} />
        <Metric label={L('已批准', 'Approved')} value={overview.governance.decision_summary.approved} icon={FileCheck2} />
        <Metric label={L('已拒绝', 'Rejected')} value={overview.governance.decision_summary.rejected} icon={BrainCircuit} />
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('治理记录', 'Governance Records')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('直接读取 P0 governance-record 正式对象。', 'Direct P0 governance-record objects.')}</p>
        <div className="mt-4">
          <FilterPills
            value={queueStatus}
            onChange={setQueueStatus}
            options={[
              { label: L('全部', 'All'), value: 'ALL' },
              { label: L('打开', 'Open'), value: 'OPEN' },
              { label: L('关闭', 'Closed'), value: 'CLOSED' },
            ]}
          />
          <div className="space-y-2">
            {records.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedObject({ object_type: 'GOVERNANCE_RECORD', object_id: item.id })}
                className="w-full rounded-2xl bg-slate-50 px-4 py-3 text-left text-sm transition hover:bg-slate-100"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.queue_status}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {item.decision_status} | {item.recommended_action} | {Math.round(item.confidence_score * 100)}%
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {L('事件', 'Event')} {item.event_id} | actor {item.actor ?? L('系统', 'system')}
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('选中治理记录', 'Selected Governance Record')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('详情来自 `/api/v1/p0/governance-records/{id}`。', 'Detail loaded from `/api/v1/p0/governance-records/{id}`.')}</p>
        <div className="mt-4">
          {!selectedObject ? (
            <div className="text-sm text-slate-500">{L('选择一个治理记录查看详情。', 'Select a governance record to inspect its detail.')}</div>
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

import { useEffect, useState } from 'react'
import { FileCheck2, ShieldCheck } from 'lucide-react'

import { GenesisApi, type P0ContractArtifact, type P0ObjectDetailState, type P0OverviewResponse } from '../services/api'
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

export default function P0ContractSurface() {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [overview, setOverview] = useState<P0OverviewResponse | null>(null)
  const [artifacts, setArtifacts] = useState<P0ContractArtifact[]>([])
  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)

  useEffect(() => {
    Promise.all([
      GenesisApi.getP0Overview(),
      GenesisApi.getP0ContractArtifacts({ limit: 20, serving_status: 'PUBLISHED' }),
    ]).then(([overviewResponse, artifactsResponse]) => {
      setOverview(overviewResponse)
      setArtifacts(artifactsResponse.items)
    })
  }, [])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }
    void GenesisApi.getP0ContractArtifactDetail(selectedObject.object_id).then(setSelectedDetail)
  }, [selectedObject])

  if (!overview) {
    return <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">{L('正在加载 Contract...', 'Loading contracts...')}</div>
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">P0 Contract</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{L('Contract 面', 'Contract surface')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {L('消费经过治理批准后发布的稳定工件。这是 P0 闭环的服务输出侧。', 'Consume the stable artifacts published after governance approval. This is the serving side of the P0 loop.')}
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <Metric label={L('生效契约', 'Active Contracts')} value={overview.contract.active_contracts} icon={FileCheck2} />
        <Metric label={L('已批准规则', 'Approved Rules')} value={overview.contract.approved_rules} icon={ShieldCheck} />
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('契约工件', 'Contract Artifacts')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('直接读取 P0 contract-artifact 正式对象。', 'Direct P0 contract-artifact objects.')}</p>
        <div className="mt-4 space-y-2">
          {artifacts.map((item) => (
            <button
              key={item.id ?? item.contract_name}
              type="button"
              onClick={() => item.id && setSelectedObject({ object_type: 'CONTRACT_ARTIFACT', object_id: item.id })}
              className="w-full rounded-2xl bg-slate-50 px-4 py-3 text-left text-sm transition hover:bg-slate-100"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">{item.contract_name}</span>
                <span className="text-slate-500">{item.serving_status}</span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {item.event_code} | {item.approved_rule_count} {L('条已批准规则', 'approved rules')}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {item.published_at ?? L('未发布', 'not published')}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('选中契约工件', 'Selected Contract Artifact')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('详情来自 `/api/v1/p0/contract-artifacts/{id}`。', 'Detail loaded from `/api/v1/p0/contract-artifacts/{id}`.')}</p>
        <div className="mt-4">
          {!selectedObject ? (
            <div className="text-sm text-slate-500">{L('选择一个契约工件查看详情。', 'Select a contract artifact to inspect its detail.')}</div>
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

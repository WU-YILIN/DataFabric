import { useEffect, useState } from 'react'
import { Network, RefreshCw } from 'lucide-react'

import { GenesisApi, type FabricSemanticDomainResponse } from '../services/api'
import { FabricEmptyState, FabricPageHeader, FabricSection, FabricStatCard } from '../components/fabricUi'

export default function FabricSemanticDomains() {
  const [response, setResponse] = useState<FabricSemanticDomainResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      setResponse(await GenesisApi.getFabricSemanticDomains())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const items = response?.items ?? []

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="主题域"
        title="主题域与语义图谱"
        description="把数据源、项目记忆和已发布契约归并到统一的主题域图谱中。主题域不再是固定分层，而是查询规划、记忆命中和契约交付的语义索引。"
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw size={15} />
            刷新
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-4">
        <FabricStatCard label="主题域数量" value={response?.summary.domain_count ?? 0} />
        <FabricStatCard label="当前主导主题域" value={response?.summary.top_domain ?? '暂无'} />
        <FabricStatCard label="命中数据源" value={items.reduce((acc, item) => acc + item.source_count, 0)} />
        <FabricStatCard label="命中记忆" value={items.reduce((acc, item) => acc + item.memory_count, 0)} />
      </div>

      <FabricSection title="主题域列表" subtitle="每个主题域由数据源、记忆和契约共同构成，查询规划会优先命中主题域，再决定执行路径。">
        {loading ? (
          <FabricEmptyState message="正在加载主题域..." />
        ) : items.length === 0 ? (
          <FabricEmptyState message="当前项目还没有形成主题域。" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {items.map((item) => (
              <div key={item.domain_key} className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-center justify-between gap-3">
                  <div className="inline-flex items-center gap-2 text-lg font-semibold text-slate-900">
                    <Network size={18} />
                    {item.label}
                  </div>
                  <div className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700">
                    分值 {item.score}
                  </div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-2xl border border-slate-200 bg-white p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">数据源</div>
                    <div className="mt-1 text-2xl font-semibold text-slate-900">{item.source_count}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">记忆</div>
                    <div className="mt-1 text-2xl font-semibold text-slate-900">{item.memory_count}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 bg-white p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">契约</div>
                    <div className="mt-1 text-2xl font-semibold text-slate-900">{item.contract_count}</div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-medium text-slate-900">证据链</div>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                    {item.evidences.map((evidence) => (
                      <li key={evidence}>{evidence}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        )}
      </FabricSection>
    </div>
  )
}

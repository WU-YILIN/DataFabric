import { useEffect, useMemo, useState } from 'react'
import { Database, RefreshCw } from 'lucide-react'

import { GenesisApi, type FabricListResponse, type FabricSourceProfile } from '../services/api'
import {
  FabricBadge,
  FabricEmptyState,
  FabricFilterSelect,
  FabricPageHeader,
  FabricPager,
  FabricSearchInput,
  FabricSection,
  FabricStatCard,
  formatFabricBytes,
} from '../components/fabricUi'

const PAGE_SIZE = 10

export default function FabricSourceProfiles() {
  const [response, setResponse] = useState<FabricListResponse<FabricSourceProfile> | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [sourceType, setSourceType] = useState('ALL')
  const [heat, setHeat] = useState('ALL')
  const [offset, setOffset] = useState(0)

  const load = async () => {
    setLoading(true)
    try {
      const data = await GenesisApi.getFabricSourceProfiles({
        q: query.trim() || undefined,
        source_type: sourceType === 'ALL' ? undefined : sourceType,
        heat: heat === 'ALL' ? undefined : heat,
        limit: PAGE_SIZE,
        offset,
      })
      setResponse(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [query, sourceType, heat, offset])

  const stats = useMemo(() => {
    const items = response?.items ?? []
    return {
      totalRows: items.reduce((acc, item) => acc + item.total_rows, 0),
      totalBytes: items.reduce((acc, item) => acc + item.estimated_bytes, 0),
      hotSources: items.filter((item) => item.heat_level === 'HOT').length,
      warmSources: items.filter((item) => item.heat_level === 'WARM').length,
    }
  }, [response])

  const sourceTypeOptions = useMemo(
    () =>
      [
        { label: '全部类型', value: 'ALL' },
        ...((response?.facets?.source_types as string[] | undefined) ?? []).map((value) => ({ label: value, value })),
      ] satisfies Array<{ label: string; value: string }>,
    [response],
  )

  const heatOptions = useMemo(
    () =>
      [
        { label: '全部冷热', value: 'ALL' },
        ...((response?.facets?.heat_levels as string[] | undefined) ?? []).map((value) => ({ label: value, value })),
      ] satisfies Array<{ label: string; value: string }>,
    [response],
  )

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="源画像"
        title="源画像与冷热分布"
        description="把接入实例抽象成统一的源画像：对象规模、冷热等级、更新节奏、关键字段候选、主题域候选和物化建议都会先在这里收敛，作为查询规划与物化策略的输入。"
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
        <FabricStatCard label="当前命中数据源" value={response?.total ?? 0} hint="按筛选条件收敛后的源画像" />
        <FabricStatCard label="热点源" value={stats.hotSources} hint="优先考虑生成热点契约或物化工件" />
        <FabricStatCard label="温源" value={stats.warmSources} hint="可根据复用率晋升为热点工件" />
        <FabricStatCard label="估算空间" value={formatFabricBytes(stats.totalBytes)} hint={`约 ${stats.totalRows.toLocaleString()} 行`} />
      </div>

      <FabricSection
        title="源画像列表"
        subtitle="支持搜索、类型筛选和冷热筛选，优先定位值得进入主题域、契约和热点服务层的源。"
      >
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
          <FabricSearchInput
            value={query}
            placeholder="搜索数据源、类型或主题域"
            onChange={(value) => {
              setQuery(value)
              setOffset(0)
            }}
          />
          <FabricFilterSelect
            value={sourceType}
            onChange={(value) => {
              setSourceType(value)
              setOffset(0)
            }}
            options={sourceTypeOptions}
          />
          <FabricFilterSelect
            value={heat}
            onChange={(value) => {
              setHeat(value)
              setOffset(0)
            }}
            options={heatOptions}
          />
        </div>

        <div className="mt-5">
          {loading ? (
            <FabricEmptyState message="正在加载源画像..." />
          ) : (response?.items.length ?? 0) === 0 ? (
            <FabricEmptyState message="当前筛选条件下没有源画像结果。" />
          ) : (
            <div className="space-y-3">
              {(response?.items ?? []).map((item) => (
                <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="inline-flex items-center gap-2 font-semibold text-slate-900">
                          <Database size={16} />
                          {item.source_name}
                        </div>
                        <FabricBadge value={item.source_type} />
                        <FabricBadge value={item.heat_level} tone="heat" />
                        <FabricBadge value={item.update_mode} />
                      </div>
                      <div className="mt-2 text-sm text-slate-600">
                        共 {item.total_objects} 个对象，约 {item.total_rows.toLocaleString()} 行，空间 {formatFabricBytes(item.estimated_bytes)}，
                        刷新节奏 {item.refresh_cadence}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                        {item.domain_candidates.map((domain) => (
                          <span key={domain} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
                            主题域：{domain}
                          </span>
                        ))}
                        {item.key_candidates.slice(0, 4).map((candidate) => (
                          <span key={candidate} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
                            主键候选：{candidate}
                          </span>
                        ))}
                        {item.time_candidates.slice(0, 4).map((candidate) => (
                          <span key={candidate} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
                            时间候选：{candidate}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="min-w-[280px] rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
                      <div className="font-medium text-slate-900">物化建议</div>
                      <div className="mt-2 leading-6">{item.materialization_reason}</div>
                      <div className="mt-3 text-xs text-slate-500">
                        最近扫描：{item.last_scanned_at ? new Date(item.last_scanned_at).toLocaleString() : '暂无'}
                      </div>
                    </div>
                  </div>

                  {item.top_objects.length > 0 ? (
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      {item.top_objects.map((object) => (
                        <div key={object.name} className="rounded-2xl border border-slate-200 bg-white p-3">
                          <div className="truncate font-medium text-slate-900">{object.name}</div>
                          <div className="mt-1 text-xs text-slate-500">{object.rows.toLocaleString()} 行</div>
                          <div className="mt-2">
                            <FabricBadge value={object.heat_level} tone="heat" />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
          {response ? (
            <FabricPager total={response.total} limit={response.limit} offset={response.offset} onChange={setOffset} />
          ) : null}
        </div>
      </FabricSection>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Layers3, RefreshCw } from 'lucide-react'

import {
  GenesisApi,
  type FabricListResponse,
  type FabricMaterialization,
  type FabricMaterializationArtifact,
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

const PAGE_SIZE = 10

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

export default function FabricMaterializations() {
  const [recommendations, setRecommendations] = useState<FabricListResponse<FabricMaterialization> | null>(null)
  const [artifacts, setArtifacts] = useState<FabricListResponse<FabricMaterializationArtifact> | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('ALL')
  const [heat, setHeat] = useState('ALL')
  const [offset, setOffset] = useState(0)

  const load = async () => {
    setLoading(true)
    try {
      const [nextArtifacts, nextRecommendations] = await Promise.all([
        GenesisApi.getFabricMaterializationArtifacts({
          q: query.trim() || undefined,
          status: status === 'ALL' ? undefined : status,
          heat: heat === 'ALL' ? undefined : heat,
          limit: PAGE_SIZE,
          offset,
        }),
        GenesisApi.getFabricMaterializations({
          q: query.trim() || undefined,
          status: status === 'ALL' ? undefined : status,
          limit: PAGE_SIZE,
          offset: 0,
        }),
      ])
      setArtifacts(nextArtifacts)
      setRecommendations(nextRecommendations)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [query, status, heat, offset])

  const stats = useMemo(() => {
    const items = artifacts?.items ?? []
    return {
      total: artifacts?.total ?? 0,
      hot: items.filter((item) => item.heat_level === 'HOT').length,
      recommended: items.filter((item) => item.status === 'RECOMMENDED').length,
      promoted: items.filter((item) => item.status === 'PROMOTED' || item.status === 'READY').length,
      advisory: recommendations?.total ?? 0,
    }
  }, [artifacts, recommendations])

  return (
    <div className="space-y-6">
      <FabricPageHeader
        eyebrow="物化中心"
        title="自适应物化中心"
        description="系统不再依赖固定的 DWD / DWS 分层，而是根据问题热度、复用度、延迟目标和执行成本，持续管理临时工件、热点工件和契约结果。"
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-[16px] border border-[var(--df-border)] bg-[var(--df-surface)] px-4 py-2 text-sm font-medium text-[var(--df-text)] hover:bg-[var(--df-surface-2)]"
          >
            <RefreshCw size={15} />
            刷新
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-5">
        <FabricStatCard label="工件总数" value={stats.total} hint="当前可追踪的物化结果" />
        <FabricStatCard label="热点工件" value={stats.hot} hint="高频命中的热工件" />
        <FabricStatCard label="待确认建议" value={stats.recommended} hint="尚未正式落地" />
        <FabricStatCard label="长期工件" value={stats.promoted} hint="已晋升或可长期保留" />
        <FabricStatCard label="启发式建议" value={stats.advisory} hint="系统推荐的候选结果" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)]">
        <FabricSection title="物化工件列表" subtitle="所有物化对象都支持分页、搜索和冷热筛选，默认只展示当前页结果。">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
            <FabricSearchInput
              value={query}
              placeholder="搜索工件名称、原因或 trace"
              onChange={(value) => {
                setQuery(value)
                setOffset(0)
              }}
            />
            <FabricFilterSelect
              value={status}
              onChange={(value) => {
                setStatus(value)
                setOffset(0)
              }}
              options={[
                { label: '全部状态', value: 'ALL' },
                { label: 'RECOMMENDED', value: 'RECOMMENDED' },
                { label: 'READY', value: 'READY' },
                { label: 'PROMOTED', value: 'PROMOTED' },
                { label: 'ARCHIVED', value: 'ARCHIVED' },
              ]}
            />
            <FabricFilterSelect
              value={heat}
              onChange={(value) => {
                setHeat(value)
                setOffset(0)
              }}
              options={[
                { label: '全部冷热', value: 'ALL' },
                { label: 'HOT', value: 'HOT' },
                { label: 'WARM', value: 'WARM' },
                { label: 'COLD', value: 'COLD' },
              ]}
            />
          </div>

          <div className="mt-5">
            {loading ? (
              <FabricEmptyState message="正在加载物化工件..." />
            ) : (artifacts?.items.length ?? 0) === 0 ? (
              <FabricEmptyState message="当前筛选条件下没有物化工件。" />
            ) : (
              <div className="space-y-3">
                {(artifacts?.items ?? []).map((item) => (
                  <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="inline-flex items-center gap-2 font-semibold text-slate-900">
                            <Layers3 size={16} />
                            {item.artifact_name}
                          </div>
                          <FabricBadge value={item.artifact_type} />
                          <FabricBadge value={item.status} />
                          <FabricBadge value={item.heat_level} tone="heat" />
                        </div>
                        <div className="mt-2 text-sm text-slate-600">
                          引擎：{item.engine_key || '未指定'} · 存储策略：{item.storage_strategy || '未指定'} · 保留策略：
                          {item.retention_policy || '未指定'}
                        </div>
                        <div className="mt-2 break-all text-xs text-slate-500">
                          Trace：{item.trace_id} · 最近更新时间：{formatDateTime(item.updated_at)}
                        </div>
                        {item.expires_at ? (
                          <div className="mt-1 text-xs text-slate-500">到期时间：{formatDateTime(item.expires_at)}</div>
                        ) : null}
                      </div>
                      <div className="min-w-[320px] rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600">
                        {item.reason}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {artifacts ? <FabricPager total={artifacts.total} limit={artifacts.limit} offset={artifacts.offset} onChange={setOffset} /> : null}
          </div>
        </FabricSection>

        <div className="space-y-6">
          <FabricSection title="系统推荐" subtitle="这里展示规划器和物化策略层给出的启发式建议，用来和已存在工件做对照。">
            {recommendations && recommendations.items.length > 0 ? (
              <div className="space-y-3">
                {recommendations.items.slice(0, 8).map((item) => (
                  <div key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-semibold text-slate-900">{item.artifact_name}</div>
                      <FabricBadge value={item.artifact_type} />
                      <FabricBadge value={item.status} />
                      <FabricBadge value={item.heat_level} tone="heat" />
                    </div>
                    <div className="mt-2 text-sm text-slate-600">{item.reason}</div>
                    <div className="mt-3 text-xs text-slate-500">
                      来源：{item.source_name} · 加速层级：{item.acceleration_tier} · 延迟目标：{item.latency_target_ms}ms
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <FabricEmptyState message="当前没有启发式建议。" />
            )}
          </FabricSection>

          <FabricSection title="物化策略说明" subtitle="当前系统不会自动正式落地任何高成本物化，所有建议都需要人工确认。">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
              <div>1. 高频命中的结果优先进入热点工件候选。</div>
              <div>2. 重型异步任务完成后，系统会给出“是否晋升为长期工件”的建议。</div>
              <div>3. 未确认的物化建议只保留为候选，不自动进入正式契约和公共能力层。</div>
              <div>4. 物化中心会持续参考查询热度、执行成本、鲜度要求和遥测反馈来调整建议。</div>
            </div>
          </FabricSection>
        </div>
      </div>
    </div>
  )
}

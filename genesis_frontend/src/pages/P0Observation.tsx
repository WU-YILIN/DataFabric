import { useEffect, useState } from 'react'
import { Eye, Network } from 'lucide-react'

import { GenesisApi, type P0ObjectDetailState, type P0OverviewResponse, type P0SourceProfile } from '../services/api'
import { useLanguage } from '../i18n/language'

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

function Metric({
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

export default function P0Observation() {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (isZh ? cn : en)
  const [overview, setOverview] = useState<P0OverviewResponse | null>(null)
  const [sourceProfiles, setSourceProfiles] = useState<P0SourceProfile[]>([])
  const [heat, setHeat] = useState('ALL')
  const [selectedObject, setSelectedObject] = useState<P0ObjectDetailState | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<unknown>(null)

  useEffect(() => {
    Promise.all([
      GenesisApi.getP0Overview(),
      GenesisApi.getP0SourceProfiles({ limit: 20, heat: heat === 'ALL' ? undefined : heat }),
    ]).then(([overviewResponse, sourceProfilesResponse]) => {
      setOverview(overviewResponse)
      setSourceProfiles(sourceProfilesResponse.items)
    })
  }, [heat])

  useEffect(() => {
    if (!selectedObject) {
      setSelectedDetail(null)
      return
    }

    void GenesisApi.getP0SourceProfileDetail(selectedObject.object_id).then(setSelectedDetail)
  }, [selectedObject])

  if (!overview) {
    return <div className="flex min-h-[40vh] items-center justify-center text-sm text-slate-500">{L('正在加载 Observation...', 'Loading observation...')}</div>
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
        <div className="text-xs uppercase tracking-[0.16em] text-slate-500">P0 Observation</div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{L('Observation 工作台', 'Observation workbench')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {L('在任何语义判断开始前，先查看原始源活跃度、热度和未知信号。', 'Inspect raw source activity, heat, and unknown signals before any semantic judgment starts.')}
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <Metric label={L('日志总量', 'Total Logs')} value={overview.observation.total_logs} icon={Eye} />
        <Metric label={L('近 7 天事件', 'Events 7d')} value={overview.observation.events_7d} icon={Network} />
        <Metric label={L('活跃通道', 'Active Channels')} value={overview.observation.active_channels} icon={Network} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('热点来源', 'Top Sources')}</h3>
          <p className="mt-1 text-sm text-slate-500">{L('平台当前观测到的高流量来源。', 'Highest-volume sources currently seen by the platform.')}</p>
          <div className="mt-4 space-y-2">
            {overview.observation.top_sources.map((item) => (
              <div key={item.event_name} className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <span className="font-medium text-slate-900">{item.event_name}</span>
                <span className="text-slate-500">{item.event_count}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('未知信号', 'Unknown Signals')}</h3>
          <p className="mt-1 text-sm text-slate-500">{L('等待进入 inference 的高频未映射观测信号。', 'High-frequency unmapped observations waiting for inference.')}</p>
          <div className="mt-4 space-y-2">
            {overview.observation.unknown_signals.map((item) => (
              <div key={item.id} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.target_field}</span>
                  <span className="text-slate-500">{item.field_frequency}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {L('事件', 'Event')} {item.event_id} | {item.source_paths.join(', ')}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('源画像对象', 'Source Profiles')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('直接读取 P0 source-profile 正式对象。', 'Direct P0 source-profile objects.')}</p>
        <div className="mt-4">
          <FilterPills
            value={heat}
            onChange={setHeat}
            options={[
              { label: L('全部', 'All'), value: 'ALL' },
              { label: L('高热', 'Hot'), value: 'HOT' },
              { label: L('温', 'Warm'), value: 'WARM' },
              { label: L('冷', 'Cold'), value: 'COLD' },
            ]}
          />
          <div className="space-y-2">
            {sourceProfiles.map((item) => (
              <button
                key={`${item.id ?? item.channel_id}-${item.event_name}`}
                type="button"
                onClick={() => item.id && setSelectedObject({ object_type: 'SOURCE_PROFILE', object_id: item.id })}
                className="w-full rounded-2xl bg-slate-50 px-4 py-3 text-left text-sm transition hover:bg-slate-100"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-900">{item.event_name}</span>
                  <span className="text-slate-500">{item.heat}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {L('通道', 'Channel')} {item.channel_id} | {item.accepted_events}/{item.total_events} {L('已接收', 'accepted')} | {item.sdk_version ?? L('未知 SDK', 'unknown sdk')}
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold tracking-tight text-slate-900">{L('选中源画像', 'Selected Source Profile')}</h3>
        <p className="mt-1 text-sm text-slate-500">{L('详情来自 `/api/v1/p0/source-profiles/{id}`。', 'Detail loaded from `/api/v1/p0/source-profiles/{id}`.')}</p>
        <div className="mt-4">
          {!selectedObject ? (
            <div className="text-sm text-slate-500">{L('选择一个源画像查看详情。', 'Select a source profile to inspect its detail.')}</div>
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

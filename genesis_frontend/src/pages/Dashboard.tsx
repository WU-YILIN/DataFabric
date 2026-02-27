import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Gauge,
  ListChecks,
  ShieldCheck,
  Siren,
} from 'lucide-react'

import { clsx } from 'clsx'
import {
  GenesisApi,
  type OverviewActivityItem,
  type OverviewResponse,
  type OverviewTodoItem,
} from '../services/api'
import { useLanguage } from '../i18n/language'

const StatCard = ({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: any
  label: string
  value: string | number
  tone: string
}) => (
  <div className="glass p-5 rounded-2xl flex items-center gap-4">
    <div className={clsx('p-3 rounded-xl text-white shadow-md', tone)}>
      <Icon size={20} />
    </div>
    <div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-slate-900 tracking-tight">{value}</p>
    </div>
  </div>
)

const Dashboard = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    GenesisApi.getOverview()
      .then(setOverview)
      .catch((e: any) => {
        setError(e?.response?.data?.message ?? (isZh ? '加载总览数据失败' : 'Failed to load overview data'))
      })
  }, [isZh])

  const recentActivity: OverviewActivityItem[] = useMemo(
    () => overview?.recent_activity.slice(0, 8) ?? [],
    [overview],
  )
  const topTodos: OverviewTodoItem[] = useMemo(() => overview?.todos.slice(0, 8) ?? [], [overview])

  if (!overview) {
    if (error) {
      return (
        <div className="glass rounded-2xl p-8 text-rose-700 border border-rose-100">
          <h3 className="font-bold mb-2">{isZh ? '总览加载失败' : 'Overview load failed'}</h3>
          <p className="text-sm">{error}</p>
        </div>
      )
    }
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="w-10 h-10 border-4 border-cyan-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
      <header className="mb-8">
        <h2 className="text-3xl font-bold text-slate-900 tracking-tight">{isZh ? '总览' : 'Overview'}</h2>
        <p className="text-slate-500 text-base">
          {isZh
            ? '基于租户/项目隔离展示治理活动、风险状态与待办事项。'
            : 'Tenant/project scoped status with governance activity, risks, and pending actions.'}
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 mb-8">
        <StatCard icon={Database} label={isZh ? '事件总数' : 'Total Events'} value={overview.kpis.total_events} tone="bg-cyan-600" />
        <StatCard
          icon={ShieldCheck}
          label={isZh ? '30 天治理检查' : 'Governance Checks (30d)'}
          value={overview.kpis.governance_checks_30d}
          tone="bg-emerald-600"
        />
        <StatCard
          icon={Gauge}
          label={isZh ? '审批通过率' : 'Approval Rate'}
          value={overview.kpis.approval_rate != null ? `${Math.round(overview.kpis.approval_rate * 100)}%` : isZh ? '暂无' : 'N/A'}
          tone="bg-amber-500"
        />
        <StatCard icon={Activity} label={isZh ? '活跃 Pipelines' : 'Active Pipelines'} value={overview.kpis.active_pipelines} tone="bg-indigo-600" />
        <StatCard icon={AlertTriangle} label={isZh ? '失败 Pipelines' : 'Failed Pipelines'} value={overview.kpis.failed_pipelines} tone="bg-rose-500" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="glass rounded-2xl p-6 xl:col-span-2">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-xl font-bold text-slate-900 tracking-tight">{isZh ? '最近活动' : 'Recent Activity'}</h3>
            <span className="text-xs text-slate-500">
              {recentActivity.length} {isZh ? '条' : 'items'}
            </span>
          </div>
          <div className="space-y-3">
            {recentActivity.length === 0 && <p className="text-sm text-slate-500">{isZh ? '暂无最近活动。' : 'No recent activity.'}</p>}
            {recentActivity.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-xl border border-slate-100 bg-white/70 px-4 py-3"
              >
                <div>
                  <p className="font-semibold text-slate-900 text-sm">
                    {isZh ? `${item.action} -> ${item.target}` : `${item.action} on ${item.target}`}
                  </p>
                  <p className="text-xs text-slate-500">
                    {item.user} | {new Date(item.timestamp).toLocaleString()}
                  </p>
                </div>
                <span
                  className={clsx(
                    'px-2 py-1 rounded-full text-xs font-semibold',
                    item.status === 'SUCCESS'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-rose-100 text-rose-700',
                  )}
                >
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="glass rounded-2xl p-6">
            <h3 className="text-xl font-bold text-slate-900 tracking-tight mb-4">{isZh ? '风险' : 'Risks'}</h3>
            <div className="space-y-3 text-sm">
              <div className="rounded-xl border border-rose-100 bg-rose-50/60 p-3">
                <div className="flex items-center gap-2 text-rose-700 font-semibold">
                  <Siren size={16} /> {isZh ? '未处理告警' : 'Unhandled Alerts'}
                </div>
                <p className="text-slate-600 mt-1">{overview.risks.unhandled_alerts.length} {isZh ? '个待处理' : 'open'}</p>
              </div>
              <div className="rounded-xl border border-amber-100 bg-amber-50/70 p-3">
                <div className="flex items-center gap-2 text-amber-700 font-semibold">
                  <ShieldCheck size={16} /> {isZh ? '高风险事件' : 'High-Risk Events'}
                </div>
                <p className="text-slate-600 mt-1">{overview.risks.high_risk_events.length} {isZh ? '个待审查' : 'pending review'}</p>
              </div>
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-3">
                <div className="flex items-center gap-2 text-indigo-700 font-semibold">
                  <Activity size={16} /> {isZh ? '异常 Pipelines' : 'Unhealthy Pipelines'}
                </div>
                <p className="text-slate-600 mt-1">{overview.risks.pipelines.length} {isZh ? '个受影响' : 'impacted'}</p>
              </div>
            </div>
          </div>

          <div className="glass rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-slate-900 tracking-tight">{isZh ? '待办事项' : 'Todos'}</h3>
              <ListChecks size={18} className="text-slate-400" />
            </div>
            <div className="space-y-3">
              {topTodos.length === 0 && <p className="text-sm text-slate-500">{isZh ? '暂无待办事项。' : 'No open todo items.'}</p>}
              {topTodos.map((todo) => (
                <div key={todo.id} className="rounded-xl border border-slate-100 bg-white/70 px-3 py-3">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-semibold text-slate-900 line-clamp-1">{todo.title}</p>
                    <span
                      className={clsx(
                        'text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full',
                        todo.priority === 'CRITICAL'
                          ? 'bg-rose-100 text-rose-700'
                          : todo.priority === 'HIGH'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-slate-100 text-slate-600',
                      )}
                    >
                      {todo.priority}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-2">{todo.description}</p>
                  <div className="mt-2 text-[11px] text-slate-500 flex items-center gap-1">
                    <CheckCircle2 size={12} /> {todo.target.type}:{todo.target.label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard

import { useMemo, useState } from 'react'
import { Building2, FolderKanban, ShieldCheck } from 'lucide-react'
import { useSession } from '../auth/session'
import { useLanguage } from '../i18n/language'

const TenantAdmin = () => {
  const { locale } = useLanguage()
  const isZh = locale === 'zh-CN'
  const { tenants, activeTenantId, activeProjectId, switchTenant, switchProject, isSwitchingContext } = useSession()

  const [statusMap, setStatusMap] = useState<Record<number, 'ACTIVE' | 'FROZEN'>>({})

  const rows = useMemo(
    () =>
      tenants.map((t) => ({
        id: t.id,
        name: t.name,
        projects: t.projects,
        status: statusMap[t.id] ?? 'ACTIVE',
      })),
    [tenants, statusMap],
  )

  const toggleStatus = (tenantId: number) => {
    setStatusMap((prev) => ({
      ...prev,
      [tenantId]: (prev[tenantId] ?? 'ACTIVE') === 'ACTIVE' ? 'FROZEN' : 'ACTIVE',
    }))
  }

  return (
    <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <header className="rounded-2xl border border-slate-200 bg-white/80 p-5">
        <h2 className="text-2xl font-bold text-slate-900">{isZh ? '租户与项目管理' : 'Tenant & Project Admin'}</h2>
        <p className="mt-1 text-sm text-slate-600">
          {isZh
            ? '集中管理租户、项目与状态。可快速切换上下文，控制启停状态（演示版）。'
            : 'Centralized tenant/project operations with quick context switching and status control (demo mode).'}
        </p>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-lg font-semibold text-slate-900 mb-3">{isZh ? '当前上下文' : 'Current Context'}</h3>
        <div className="text-sm text-slate-600">
          {isZh ? '租户ID' : 'Tenant ID'}: <span className="font-semibold text-slate-900">{activeTenantId ?? '-'}</span>
          {' · '}
          {isZh ? '项目ID' : 'Project ID'}: <span className="font-semibold text-slate-900">{activeProjectId ?? '-'}</span>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2">{isZh ? '租户' : 'Tenant'}</th>
              <th className="py-2">{isZh ? '项目数' : 'Projects'}</th>
              <th className="py-2">{isZh ? '状态' : 'Status'}</th>
              <th className="py-2">{isZh ? '操作' : 'Actions'}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-slate-100 align-top">
                <td className="py-3">
                  <div className="flex items-center gap-2 font-semibold text-slate-900">
                    <Building2 size={14} /> {row.name}
                  </div>
                  <div className="mt-2 space-y-1">
                    {row.projects.slice(0, 4).map((p) => (
                      <button
                        key={p.id}
                        onClick={() => void switchProject(p.id)}
                        disabled={isSwitchingContext}
                        className="mr-2 inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                      >
                        <FolderKanban size={12} /> {p.name}
                      </button>
                    ))}
                  </div>
                </td>
                <td className="py-3 text-slate-700">{row.projects.length}</td>
                <td className="py-3">
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-semibold ${
                      row.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="py-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => void switchTenant(row.id)}
                      disabled={isSwitchingContext}
                      className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      {isZh ? '切换到此租户' : 'Switch Tenant'}
                    </button>
                    <button
                      onClick={() => toggleStatus(row.id)}
                      className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      {row.status === 'ACTIVE' ? (isZh ? '冻结' : 'Freeze') : isZh ? '恢复' : 'Resume'}
                    </button>
                    <button className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50">
                      <span className="inline-flex items-center gap-1"><ShieldCheck size={12} />{isZh ? '权限' : 'Access'}</span>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

export default TenantAdmin

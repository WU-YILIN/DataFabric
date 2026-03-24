import { FolderKanban, Layers3 } from 'lucide-react'

import { useSession } from '../auth/session'
import { getConfirmedProjectId, setConfirmedProjectId } from '../utils/workspaceSelection'

export default function ProjectManagement() {
  const {
    tenants,
    activeTenantId,
    activeProjectId,
    isSwitchingContext,
    switchTenant,
    switchProject,
  } = useSession()
  const confirmedProjectId = getConfirmedProjectId()

  const handleUseProject = async (tenantId: number, projectId: number) => {
    if (tenantId !== activeTenantId) {
      await switchTenant(tenantId)
      setConfirmedProjectId(null)
      window.dispatchEvent(new Event('storage'))
      return
    }

    if (projectId !== activeProjectId) {
      await switchProject(projectId)
    }

    setConfirmedProjectId(projectId)
    window.dispatchEvent(new Event('storage'))
  }

  return (
    <div className="space-y-6">
      <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl bg-slate-100 p-3 text-slate-700">
            <FolderKanban size={20} />
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">项目管理</h1>
            <p className="mt-1 text-sm text-slate-500">
              先确认工作项目，再开启 AI 对话、知识检索和会话管理。所有会话、记忆和知识上下文都按项目隔离。
            </p>
          </div>
        </div>
      </section>

      <div className="space-y-5">
        {tenants.map((tenant) => (
          <section key={tenant.id} className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">工作区</div>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{tenant.name}</h2>
                <div className="mt-1 text-sm text-slate-500">
                  选择一个项目作为当前 AI 对话、记忆检索和会话保存的上下文。
                </div>
              </div>
              <button
                onClick={() => void switchTenant(tenant.id)}
                disabled={isSwitchingContext}
                className="rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {tenant.id === activeTenantId ? '当前租户' : '切换租户'}
              </button>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {tenant.projects.map((project) => {
                const isActive = tenant.id === activeTenantId && project.id === activeProjectId
                const isConfirmed = project.id === confirmedProjectId

                return (
                  <div
                    key={project.id}
                    className={`rounded-3xl border p-5 transition ${
                      isConfirmed
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-slate-50 text-slate-900'
                    }`}
                  >
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wide opacity-75">
                      <Layers3 size={14} />
                      项目
                    </div>
                    <div className="mt-3 text-lg font-semibold tracking-tight">{project.name}</div>
                    <div className={`mt-1 text-sm ${isConfirmed ? 'text-slate-200' : 'text-slate-500'}`}>
                      角色：{project.role}
                    </div>
                    <div className={`mt-4 text-sm leading-6 ${isConfirmed ? 'text-slate-100' : 'text-slate-600'}`}>
                      {isConfirmed
                        ? '当前项目已经成为 AI 对话、知识检索和会话保存的默认上下文。'
                        : '点击“使用此项目”，解锁聊天、AI 记忆和项目内的知识工作流。'}
                    </div>
                    <div className="mt-5 flex gap-3">
                      <button
                        onClick={() => void handleUseProject(tenant.id, project.id)}
                        disabled={isSwitchingContext || tenant.id !== activeTenantId}
                        className={`rounded-2xl px-4 py-2 text-sm font-medium transition ${
                          isConfirmed
                            ? 'bg-white/15 text-white'
                            : 'bg-slate-900 text-white hover:bg-slate-800'
                        } disabled:cursor-not-allowed disabled:opacity-60`}
                      >
                        {isConfirmed ? '使用中' : '使用此项目'}
                      </button>
                    </div>
                    {isActive && !isConfirmed ? (
                      <div className="mt-3 text-xs text-amber-500">
                        当前项目已激活，但尚未确认为 AI 对话上下文。
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Beaker,
  BookOpen,
  Boxes,
  Building2,
  CalendarClock,
  Cable,
  Database,
  DollarSign,
  FileText,
  FlaskConical,
  History,
  KeyRound,
  LayoutDashboard,
  Scale,
  SearchCode,
  Server,
  ShieldCheck,
  Rocket,
  Users2,
  Wifi,
  Workflow,
} from 'lucide-react'

import { useSession } from './auth/session'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Governance from './pages/Governance'
import Events from './pages/Events'
import AISpecCenter from './pages/AISpecCenter'
import AIDedupReuseCenter from './pages/AIDedupReuseCenter'
import Pipelines from './pages/Pipelines'
import DataCatalog from './pages/DataCatalog'
import DataQuality from './pages/DataQuality'
import Explore from './pages/Explore'
import Infrastructure from './pages/Infrastructure'
import Scheduler from './pages/Scheduler'
import AuditLogs from './pages/AuditLogs'
import SettingsPage from './pages/Settings'
import MonitoringAlerts from './pages/MonitoringAlerts'
import CollaborationWorkflowPage from './pages/CollaborationWorkflow'
import KnowledgeDocs from './pages/KnowledgeDocs'
import CostUsageAnalytics from './pages/CostUsageAnalytics'
import SandboxExperimentation from './pages/SandboxExperimentation'
import IntegrationHub from './pages/IntegrationHub'
import AccessManagementPage from './pages/AccessManagement'
import PolicyRuleCenterPage from './pages/PolicyRuleCenter'
import IngestionSdkCenter from './pages/IngestionSdkCenter'
import ReleaseChangeManagement from './pages/ReleaseChangeManagement'
import CustomReportsDashboardBuilder from './pages/CustomReportsDashboardBuilder'
import DataProductMarketplace from './pages/DataProductMarketplace'
import IncidentResponseCenter from './pages/IncidentResponseCenter'
import TenantAdmin from './pages/TenantAdmin'
import { useLanguage } from './i18n/language'

type SidebarEntry = { to: string; icon: any; zh: string; en: string }

const primaryFlow: SidebarEntry[] = [
  { to: '/', icon: LayoutDashboard, zh: '总览', en: 'Dashboard' },
  { to: '/ai-spec', icon: Database, zh: 'AI 规范', en: 'AI Spec' },
  { to: '/ai-dedup', icon: SearchCode, zh: 'AI 查重', en: 'AI Dedup' },
  { to: '/events', icon: Database, zh: '事件', en: 'Events' },
  { to: '/governance', icon: ShieldCheck, zh: '治理', en: 'Governance' },
  { to: '/pipelines', icon: Workflow, zh: '管道', en: 'Pipelines' },
  { to: '/data-quality', icon: FlaskConical, zh: '质量', en: 'Data Quality' },
  { to: '/scheduler', icon: CalendarClock, zh: '调度', en: 'Scheduler' },
  { to: '/monitoring', icon: Activity, zh: '监控', en: 'Monitoring' },
  { to: '/cost', icon: DollarSign, zh: '成本', en: 'Cost' },
]

const advancedFlow: SidebarEntry[] = [
  { to: '/catalog', icon: BookOpen, zh: '目录', en: 'Catalog' },
  { to: '/explore', icon: SearchCode, zh: '探索', en: 'Explore' },
  { to: '/infrastructure', icon: Server, zh: '基础设施', en: 'Infrastructure' },
  { to: '/integration-hub', icon: Cable, zh: '集成中心', en: 'Integration Hub' },
  { to: '/access', icon: KeyRound, zh: '权限', en: 'Access' },
  { to: '/incidents', icon: AlertTriangle, zh: '事件响应', en: 'Incidents' },
  { to: '/collaboration', icon: Users2, zh: '协作', en: 'Collaboration' },
  { to: '/knowledge', icon: FileText, zh: '知识库', en: 'Knowledge' },
  { to: '/logs', icon: History, zh: '审计日志', en: 'Audit Logs' },
  { to: '/policy-center', icon: Scale, zh: '策略中心', en: 'Policy Center' },
  { to: '/release-center', icon: Rocket, zh: '发布中心', en: 'Release Center' },
  { to: '/reports', icon: BarChart3, zh: '报表', en: 'Reports' },
  { to: '/marketplace', icon: Boxes, zh: '市场', en: 'Marketplace' },
  { to: '/tenant-admin', icon: Building2, zh: '租户管理', en: 'Tenant Admin' },
  { to: '/ingestion', icon: Wifi, zh: '接入 SDK', en: 'Ingestion SDK' },
  { to: '/sandbox', icon: Beaker, zh: '沙箱', en: 'Sandbox' },
]

const SidebarItem = ({ to, icon: Icon, label }: { to: string; icon: any; label: string }) => {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      to={to}
      className={clsx(
        'group flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm transition-all duration-200',
        isActive
          ? 'bg-black text-white shadow-sm'
          : 'text-slate-600 hover:bg-white hover:text-slate-900 border border-transparent hover:border-slate-200',
      )}
    >
      <Icon size={16} className={clsx(isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-600')} />
      <span className="font-medium tracking-tight">{label}</span>
    </Link>
  )
}

function App() {
  const { t, locale, setLocale } = useLanguage()
  const zh = locale === 'zh-CN'
  const L = (cn: string, en: string) => (zh ? cn : en)
  const {
    isLoading,
    isSwitchingContext,
    contextVersion,
    isAuthenticated,
    user,
    tenants,
    activeTenantId,
    activeProjectId,
    activeTenant,
    logout,
    switchTenant,
    switchProject,
  } = useSession()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f5f5f7]">
        <div className="w-10 h-10 border-4 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    )
  }

  if (!activeTenant || activeProjectId == null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f5f5f7] text-slate-600">
        {t('app.noProject')}
      </div>
    )
  }

  return (
    <div className="min-h-screen w-full bg-[#f5f5f7] text-slate-900">
      <div className="mx-auto max-w-[1560px] px-4 py-4 md:px-6 md:py-6">
        <div className="relative z-30 mb-4 flex items-center justify-between rounded-3xl border border-white/70 bg-white/70 px-6 py-4 backdrop-blur-xl shadow-sm">
          <div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">DataFabric</div>
            <div className="text-2xl font-semibold tracking-tight">{L('构建可信数据运营', 'Build trusted data operations.')}</div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-2 py-1.5 text-xs">
              <span className="text-slate-500">{L('租户', 'Tenant')}</span>
              <select
                className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                value={activeTenantId ?? ''}
                disabled={isSwitchingContext}
                onChange={(e) => {
                  void switchTenant(Number(e.target.value))
                }}
              >
                {tenants.map((tenant) => (
                  <option key={tenant.id} value={tenant.id}>
                    {tenant.name}
                  </option>
                ))}
              </select>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">{L('项目', 'Project')}</span>
              <select
                className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs"
                value={activeProjectId}
                disabled={isSwitchingContext}
                onChange={(e) => {
                  void switchProject(Number(e.target.value))
                }}
              >
                {activeTenant.projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-1 text-xs">
              <button
                className={clsx('rounded-lg px-2 py-1', locale === 'zh-CN' ? 'bg-black text-white' : 'text-slate-600')}
                onClick={() => setLocale('zh-CN')}
              >
                中文
              </button>
              <button
                className={clsx('rounded-lg px-2 py-1', locale === 'en-US' ? 'bg-black text-white' : 'text-slate-600')}
                onClick={() => setLocale('en-US')}
              >
                EN
              </button>
            </div>
            <details className="relative z-50">
              <summary className="list-none cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold text-slate-700">
                    {(user?.name?.slice(0, 1) ?? 'U').toUpperCase()}
                  </div>
                  <div className="text-left">
                    <div className="text-sm font-semibold leading-tight">@{user?.name ?? 'user'}</div>
                    <div className="text-[11px] text-slate-500">{user?.email}</div>
                  </div>
                </div>
              </summary>
              <div className="absolute right-0 top-full z-50 mt-2 w-52 rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
                <Link to="/" className="block rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">{L('仪表盘', 'Dashboard')}</Link>
                <Link to="/settings" className="block rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">{L('设置', 'Settings')}</Link>
                <div className="my-1 h-px bg-slate-200" />
                <button onClick={logout} className="w-full rounded-lg px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50">{L('退出登录', 'Sign out')}</button>
              </div>
            </details>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="rounded-3xl border border-white/70 bg-white/70 p-4 backdrop-blur-xl shadow-sm lg:sticky lg:top-6 lg:h-[calc(100vh-96px)] lg:overflow-auto">
            <div className="mb-2 px-1 text-[11px] uppercase tracking-wider text-slate-500">{L('核心流程', 'Core Flow')}</div>
            <div className="space-y-1">
              {primaryFlow.map((item) => (
                <SidebarItem key={item.to} to={item.to} icon={item.icon} label={L(item.zh, item.en)} />
              ))}
            </div>

            <div className="mb-2 mt-5 px-1 text-[11px] uppercase tracking-wider text-slate-500">{L('高级模块', 'Advanced')}</div>
            <div className="space-y-1">
              {advancedFlow.map((item) => (
                <SidebarItem key={item.to} to={item.to} icon={item.icon} label={L(item.zh, item.en)} />
              ))}
            </div>

          </aside>

          <main className="rounded-3xl border border-white/70 bg-white/70 p-5 backdrop-blur-xl shadow-sm md:p-7">
            <Routes key={contextVersion}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/governance" element={<Governance />} />
              <Route path="/policy-center" element={<PolicyRuleCenterPage />} />
              <Route path="/release-center" element={<ReleaseChangeManagement />} />
              <Route path="/reports" element={<CustomReportsDashboardBuilder />} />
              <Route path="/marketplace" element={<DataProductMarketplace />} />
              <Route path="/tenant-admin" element={<TenantAdmin />} />
              <Route path="/ingestion" element={<IngestionSdkCenter />} />
              <Route path="/ai-spec" element={<AISpecCenter />} />
              <Route path="/ai-dedup" element={<AIDedupReuseCenter />} />
              <Route path="/events" element={<Events />} />
              <Route path="/catalog" element={<DataCatalog />} />
              <Route path="/data-quality" element={<DataQuality />} />
              <Route path="/explore" element={<Explore />} />
              <Route path="/infrastructure" element={<Infrastructure />} />
              <Route path="/integration-hub" element={<IntegrationHub />} />
              <Route path="/access" element={<AccessManagementPage />} />
              <Route path="/monitoring" element={<MonitoringAlerts />} />
              <Route path="/incidents" element={<IncidentResponseCenter />} />
              <Route path="/collaboration" element={<CollaborationWorkflowPage />} />
              <Route path="/knowledge" element={<KnowledgeDocs />} />
              <Route path="/cost" element={<CostUsageAnalytics />} />
              <Route path="/sandbox" element={<SandboxExperimentation />} />
              <Route path="/scheduler" element={<Scheduler />} />
              <Route path="/pipelines" element={<Pipelines />} />
              <Route path="/logs" element={<AuditLogs />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="*"
                element={<div className="text-slate-500 text-center mt-20">{t('app.placeholder')}</div>}
              />
            </Routes>
          </main>
        </div>
      </div>
    </div>
  )
}

export default App

import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Beaker,
  BookOpen,
  Boxes,
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
  Settings,
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
import { useLanguage } from './i18n/language'

type SidebarEntry = { to: string; icon: any; label: string }

const primaryFlow: SidebarEntry[] = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/events', icon: Database, label: 'Events' },
  { to: '/governance', icon: ShieldCheck, label: 'Governance' },
  { to: '/pipelines', icon: Workflow, label: 'Pipelines' },
  { to: '/data-quality', icon: FlaskConical, label: 'Data Quality' },
  { to: '/scheduler', icon: CalendarClock, label: 'Scheduler' },
  { to: '/monitoring', icon: Activity, label: 'Monitoring' },
  { to: '/cost', icon: DollarSign, label: 'Cost' },
]

const advancedFlow: SidebarEntry[] = [
  { to: '/catalog', icon: BookOpen, label: 'Catalog' },
  { to: '/explore', icon: SearchCode, label: 'Explore' },
  { to: '/infrastructure', icon: Server, label: 'Infrastructure' },
  { to: '/integration-hub', icon: Cable, label: 'Integration Hub' },
  { to: '/access', icon: KeyRound, label: 'Access' },
  { to: '/incidents', icon: AlertTriangle, label: 'Incidents' },
  { to: '/collaboration', icon: Users2, label: 'Collaboration' },
  { to: '/knowledge', icon: FileText, label: 'Knowledge' },
  { to: '/logs', icon: History, label: 'Audit Logs' },
  { to: '/policy-center', icon: Scale, label: 'Policy Center' },
  { to: '/release-center', icon: Rocket, label: 'Release Center' },
  { to: '/reports', icon: BarChart3, label: 'Reports' },
  { to: '/marketplace', icon: Boxes, label: 'Marketplace' },
  { to: '/ingestion', icon: Wifi, label: 'Ingestion SDK' },
  { to: '/sandbox', icon: Beaker, label: 'Sandbox' },
]

const SidebarItem = ({ to, icon: Icon, label }: SidebarEntry) => {
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
  const { t } = useLanguage()
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
        <div className="mb-4 flex items-center justify-between rounded-3xl border border-white/70 bg-white/70 px-6 py-4 backdrop-blur-xl shadow-sm">
          <div>
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">DataFabric</div>
            <div className="text-2xl font-semibold tracking-tight">Build trusted data operations.</div>
          </div>
          <div className="text-right">
            <div className="text-sm font-semibold">{user?.name}</div>
            <div className="text-xs text-slate-500">{user?.email}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="rounded-3xl border border-white/70 bg-white/70 p-4 backdrop-blur-xl shadow-sm lg:sticky lg:top-6 lg:h-[calc(100vh-96px)] lg:overflow-auto">
            <div className="mb-4 space-y-2">
              <label className="block text-[11px] uppercase tracking-wider text-slate-500">
                {t('app.tenant')}
              </label>
              <select
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
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

              <label className="block pt-2 text-[11px] uppercase tracking-wider text-slate-500">
                {t('app.project')}
              </label>
              <select
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
                value={activeProjectId}
                disabled={isSwitchingContext}
                onChange={(e) => {
                  void switchProject(Number(e.target.value))
                }}
              >
                {activeTenant.projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name} ({project.role})
                  </option>
                ))}
              </select>
            </div>

            <div className="mb-2 px-1 text-[11px] uppercase tracking-wider text-slate-500">Core Flow</div>
            <div className="space-y-1">
              {primaryFlow.map((item) => (
                <SidebarItem key={item.to} {...item} />
              ))}
            </div>

            <div className="mb-2 mt-5 px-1 text-[11px] uppercase tracking-wider text-slate-500">Advanced</div>
            <div className="space-y-1">
              {advancedFlow.map((item) => (
                <SidebarItem key={item.to} {...item} />
              ))}
            </div>

            <div className="mt-5 border-t border-slate-200 pt-3">
              <SidebarItem to="/settings" icon={Settings} label={t('nav.settings')} />
              <button
                onClick={logout}
                className="mt-2 w-full rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                {t('app.logout')}
              </button>
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
              <Route path="/ingestion" element={<IngestionSdkCenter />} />
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

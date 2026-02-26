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

const SidebarItem = ({ to, icon: Icon, label }: { to: string; icon: any; label: string }) => {
  const location = useLocation()
  const isActive = location.pathname === to

  return (
    <Link
      to={to}
      className={clsx(
        'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300',
        isActive
          ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-500/30 scale-[1.02]'
          : 'text-slate-600 hover:bg-white/60 hover:text-slate-900',
      )}
    >
      <Icon size={18} className={clsx(isActive ? 'text-white' : 'text-slate-400')} />
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
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="w-10 h-10 border-4 border-cyan-600 border-t-transparent rounded-full animate-spin" />
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
      <div className="min-h-screen flex items-center justify-center bg-slate-100 text-slate-600">
        {t('app.noProject')}
      </div>
    )
  }

  return (
    <div className="flex min-h-screen w-screen bg-[#f4f7fb]">
      <aside className="w-72 glass fixed h-full z-10 flex flex-col gap-2 p-4 border-r border-white/40">
        <div className="px-4 py-7 mb-1">
          <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Genesis</p>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight mt-2">{t('app.brand')}</h1>
        </div>

        <div className="space-y-1">
          <SidebarItem to="/" icon={LayoutDashboard} label={t('nav.overview')} />
          <SidebarItem to="/governance" icon={ShieldCheck} label={t('nav.governance')} />
          <SidebarItem to="/policy-center" icon={Scale} label={t('nav.policy')} />
          <SidebarItem to="/release-center" icon={Rocket} label={t('nav.release')} />
          <SidebarItem to="/reports" icon={BarChart3} label={t('nav.reports')} />
          <SidebarItem to="/marketplace" icon={Boxes} label={t('nav.marketplace')} />
          <SidebarItem to="/ingestion" icon={Wifi} label={t('nav.ingestion')} />
          <SidebarItem to="/events" icon={Database} label={t('nav.events')} />
          <SidebarItem to="/catalog" icon={BookOpen} label={t('nav.catalog')} />
          <SidebarItem to="/data-quality" icon={FlaskConical} label={t('nav.dataQuality')} />
          <SidebarItem to="/explore" icon={SearchCode} label={t('nav.explore')} />
          <SidebarItem to="/infrastructure" icon={Server} label={t('nav.infrastructure')} />
          <SidebarItem to="/integration-hub" icon={Cable} label={t('nav.integrationHub')} />
          <SidebarItem to="/access" icon={KeyRound} label={t('nav.access')} />
          <SidebarItem to="/monitoring" icon={Activity} label={t('nav.monitoring')} />
          <SidebarItem to="/incidents" icon={AlertTriangle} label={t('nav.incidents')} />
          <SidebarItem to="/collaboration" icon={Users2} label={t('nav.collaboration')} />
          <SidebarItem to="/knowledge" icon={FileText} label={t('nav.knowledge')} />
          <SidebarItem to="/cost" icon={DollarSign} label={t('nav.cost')} />
          <SidebarItem to="/sandbox" icon={Beaker} label={t('nav.sandbox')} />
          <SidebarItem to="/scheduler" icon={CalendarClock} label={t('nav.scheduler')} />
          <SidebarItem to="/pipelines" icon={Workflow} label={t('nav.pipelines')} />
          <SidebarItem to="/logs" icon={History} label={t('nav.logs')} />
        </div>

        <div className="mt-auto pt-4 border-t border-slate-200/60">
          <SidebarItem to="/settings" icon={Settings} label={t('nav.settings')} />
        </div>
      </aside>

      <main className="flex-1 ml-72 p-8 overflow-auto">
        <div className="max-w-7xl mx-auto">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs text-slate-500 uppercase tracking-wide">
                {t('app.tenant')}
                <select
                  className="ml-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800"
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
              </label>
              <label className="text-xs text-slate-500 uppercase tracking-wide">
                {t('app.project')}
                <select
                  className="ml-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800"
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
              </label>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-sm font-semibold text-slate-800">{user?.name}</div>
                <div className="text-xs text-slate-500">{user?.email}</div>
              </div>
              <button
                onClick={logout}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                {t('app.logout')}
              </button>
            </div>
          </div>

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
        </div>
      </main>
    </div>
  )
}

export default App

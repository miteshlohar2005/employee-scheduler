import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  Search,
  Settings,
  Sun,
  Users,
  BriefcaseBusiness,
  Building2,
} from 'lucide-react'
import { fetchSchedule, fetchStores, loginRoster, logoutRoster } from './api'
import StoreSelector from './components/StoreSelector'
import ScheduleView from './components/ScheduleView'
import MetricsRow from './components/MetricsRow'
import Sidebar from './components/Sidebar'
import MonthlyRoster from './components/MonthlyRoster'
import Management from './components/Management'
import OverviewDashboard from './components/OverviewDashboard'
import { ConflictCenter, LeaveAvailabilityView } from './components/OperationsViews'

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'monthly', label: 'Monthly Roster', icon: CalendarDays },
  { id: 'employees', label: 'Employees', icon: Users },
  { id: 'brands', label: 'Brands & Processes', icon: BriefcaseBusiness },
  { id: 'pods', label: 'Operational Pods', icon: Network },
  { id: 'leave', label: 'Leave & Availability', icon: Clock3 },
  { id: 'conflicts', label: 'Conflict Center', icon: AlertTriangle },
  { id: 'management', label: 'Management', icon: Settings },
  { id: 'weekly', label: 'Weekly Store Schedule', icon: Building2 },
]

const PAGE_LABELS = Object.fromEntries(NAV_ITEMS.map((item) => [item.id, item.label]))

function App() {
  const [activePage, setActivePage] = useState('overview')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [globalSearch, setGlobalSearch] = useState('')
  const [managementResource, setManagementResource] = useState('employees')
  const [stores, setStores] = useState([])
  const [storesLoading, setStoresLoading] = useState(true)
  const [storesError, setStoresError] = useState(null)
  const [selectedStoreId, setSelectedStoreId] = useState(null)
  const [schedule, setSchedule] = useState(null)
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [scheduleError, setScheduleError] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')
  const [timeFormat, setTimeFormat] = useState(() => localStorage.getItem('timeFormat') || '12h')
  const [authenticated, setAuthenticated] = useState(() => Boolean(sessionStorage.getItem('roster_auth_token')))
  const [authOpen, setAuthOpen] = useState(false)
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authError, setAuthError] = useState('')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }, [theme])
  useEffect(() => localStorage.setItem('timeFormat', timeFormat), [timeFormat])

  const loadStores = useCallback(async () => {
    setStoresLoading(true)
    setStoresError(null)
    try {
      const data = await fetchStores()
      setStores(data)
      setSelectedStoreId((current) =>
        current && data.some((store) => store.store_id === current)
          ? current
          : data[0]?.store_id ?? null,
      )
    } catch (err) {
      setStoresError(err.message)
    } finally {
      setStoresLoading(false)
    }
  }, [])

  useEffect(() => { loadStores() }, [loadStores])

  useEffect(() => {
    if (!selectedStoreId) {
      setSchedule(null)
      setScheduleLoading(false)
      setScheduleError(null)
      return
    }
    let cancelled = false
    setScheduleLoading(true)
    setScheduleError(null)
    fetchSchedule(selectedStoreId)
      .then((data) => { if (!cancelled) setSchedule(data) })
      .catch((err) => { if (!cancelled) setScheduleError(err.message) })
      .finally(() => { if (!cancelled) setScheduleLoading(false) })
    return () => { cancelled = true }
  }, [selectedStoreId])

  const navigate = (page, resource) => {
    setActivePage(page)
    if (resource) setManagementResource(resource)
    setMobileOpen(false)
  }

  const submitLogin = async (event) => {
    event.preventDefault()
    setAuthError('')
    try {
      const data = await loginRoster(authUsername, authPassword)
      sessionStorage.setItem('roster_auth_token', data.access_token)
      setAuthenticated(true)
      setAuthOpen(false)
      setAuthPassword('')
    } catch (err) {
      setAuthError(err.message)
    }
  }

  const submitLogout = async () => {
    try {
      await logoutRoster()
    } finally {
      setAuthenticated(false)
    }
  }

  const runGlobalSearch = (event) => {
    event.preventDefault()
    const value = globalSearch.trim().toLowerCase()
    if (!value) return
    if (value.includes('leave') || value.includes('availability')) navigate('leave')
    else if (value.includes('conflict')) navigate('conflicts')
    else if (value.includes('pod')) navigate('pods', 'pods')
    else if (value.includes('brand') || value.includes('process')) navigate('brands', 'brands')
    else navigate('employees', 'employees')
  }

  const renderPage = () => {
    switch (activePage) {
      case 'overview':
        return <OverviewDashboard onNavigate={navigate} />
      case 'monthly':
        return <MonthlyRoster onAuthRequired={() => setAuthOpen(true)} />
      case 'employees':
        return <Management initialResource="employees" />
      case 'brands':
        return <Management initialResource="brands" />
      case 'pods':
        return <Management initialResource="pods" />
      case 'leave':
        return <LeaveAvailabilityView />
      case 'conflicts':
        return <ConflictCenter />
      case 'management':
        return <Management initialResource={managementResource} />
      case 'weekly':
        return (
          <div className="space-y-5">
            <div className="page-heading">
              <div><p className="eyebrow">Legacy scheduler preserved</p><h1>Weekly store schedule</h1><p>OR-Tools hourly scheduling for operational stores.</p></div>
              <div className="flex flex-wrap items-center gap-3">
                <StoreSelector stores={stores} loading={storesLoading} error={storesError} selectedStoreId={selectedStoreId} onSelect={setSelectedStoreId} />
                <button onClick={() => setTimeFormat((value) => value === '12h' ? '24h' : '12h')} className="secondary-button">{timeFormat}</button>
              </div>
            </div>
            <MetricsRow schedule={schedule} loading={scheduleLoading} timeFormat={timeFormat} />
            <div className="mt-5 flex flex-col gap-5 lg:flex-row">
              <Sidebar employees={schedule?.eligible_employees ?? []} loading={scheduleLoading} />
              <div className="min-w-0 flex-1">
                {selectedStoreId ? (
                  <ScheduleView schedule={schedule} loading={scheduleLoading} error={scheduleError} timeFormat={timeFormat} />
                ) : (
                  <section className="glass-card rounded-2xl p-10 text-center text-sm text-slate-500">Select a store to view its weekly schedule.</section>
                )}
              </div>
            </div>
          </div>
        )
      default:
        return <OverviewDashboard onNavigate={navigate} />
    }
  }

  return (
    <div className="enterprise-app">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      {mobileOpen && <button aria-label="Close navigation" className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />}

      <aside className={`enterprise-sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-mark"><Network size={20} /></div>
          {!collapsed && (
            <div className="brand-copy">
              <strong>Datastraw</strong>
              <span>Roster OS</span>
            </div>
          )}
          <button className="collapse-button" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                className={`nav-item ${activePage === item.id ? 'active' : ''}`}
                onClick={() => {
                  if (item.id === 'management') setManagementResource('employees')
                  navigate(item.id)
                }}
                title={collapsed ? item.label : undefined}
              >
                <Icon size={18} strokeWidth={1.8} />
                {!collapsed && <span>{item.label}</span>}
                {!collapsed && item.id === 'conflicts' && <span className="nav-badge">!</span>}
              </button>
            )
          })}
        </nav>

        {!collapsed && (
          <div className="sidebar-profile">
            <div className="avatar">OS</div>
            <div><strong>Operations Lead</strong><span>Administrator</span></div>
          </div>
        )}
      </aside>

      <div className={`enterprise-main ${collapsed ? 'sidebar-collapsed' : ''}`}>
        <header className="enterprise-header">
          <div className="header-left">
            <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
            <div className="breadcrumbs">
              <span>Workspace</span>
              <ChevronRight size={13} />
              <strong>{PAGE_LABELS[activePage]}</strong>
            </div>
          </div>

          <div className="header-actions">
            <form className="global-search" onSubmit={runGlobalSearch}>
              <Search size={16} />
              <input value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} placeholder="Search employees, pods..." aria-label="Search workspace" />
              <kbd>⌘ K</kbd>
            </form>
            <button className="icon-button" onClick={() => setTheme((value) => value === 'dark' ? 'light' : 'dark')} aria-label="Toggle color theme">
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button className="secondary-button" onClick={authenticated ? submitLogout : () => setAuthOpen(true)}>
              {authenticated ? 'Sign out' : 'Admin sign in'}
            </button>
            <button className="upload-button" onClick={() => navigate('weekly')} title="Open weekly Excel/store schedule">
              <Building2 size={15} />
              <span>Store view</span>
            </button>
          </div>
        </header>

        <main className="enterprise-content">
          {renderPage()}
        </main>
      </div>
      {authOpen && (
        <div className="auth-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setAuthOpen(false)
        }}>
          <form className="auth-dialog glass-card" onSubmit={submitLogin} aria-label="Administrator sign-in">
            <p className="eyebrow">Protected operations</p>
            <h2>Administrator sign in</h2>
            <p className="auth-copy">Sign in to change data, publish rosters, and upload workbooks.</p>
            {authError && <p className="auth-error">{authError}</p>}
            <label>Username<input value={authUsername} onChange={(event) => setAuthUsername(event.target.value)} autoComplete="username" required /></label>
            <label>Password<input type="password" value={authPassword} onChange={(event) => setAuthPassword(event.target.value)} autoComplete="current-password" required /></label>
            <div className="auth-actions">
              <button type="button" className="secondary-button" onClick={() => setAuthOpen(false)}>Cancel</button>
              <button type="submit" className="primary-button">Sign in</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

export default App

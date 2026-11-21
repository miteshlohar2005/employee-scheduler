import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  CalendarDays,
  ChevronRight,
  Clock3,
  Layers3,
  ShieldCheck,
  Users,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchRosterDomain, fetchRoster, generateRoster } from '../api'

function KpiCard({ icon: Icon, label, value, detail, color = 'violet', delay = 0 }) {
  const colors = {
    violet: 'border-violet-500/20 bg-violet-500/10 text-violet-300',
    cyan: 'border-cyan-400/20 bg-cyan-400/10 text-cyan-300',
    emerald: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
    amber: 'border-amber-400/20 bg-amber-400/10 text-amber-300',
    red: 'border-red-400/20 bg-red-400/10 text-red-300',
  }
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
      whileHover={{ y: -4, scale: 1.01 }}
      className="glass-card group relative min-h-36 overflow-hidden rounded-2xl p-5"
    >
      <div className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-violet-500/5 blur-2xl transition group-hover:bg-cyan-400/10" />
      <div className="relative flex items-start justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl border ${colors[color]}`}>
          <Icon size={20} strokeWidth={1.8} />
        </div>
        <ChevronRight className="text-slate-600 transition group-hover:translate-x-1 group-hover:text-slate-400" size={17} />
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight text-slate-50">{value}</p>
      <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className="mt-2 text-xs text-slate-500">{detail}</p>
    </motion.article>
  )
}

function WorkforceOrb({ employees }) {
  const nodes = useMemo(() => employees.slice(0, 18), [employees])
  return (
    <div className="workforce-orb relative mx-auto h-[260px] w-full max-w-[390px]" aria-label="3D workforce visualization">
      <div className="orb-core absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full">
        <Users size={34} className="text-cyan-200" />
      </div>
      <div className="orb-ring orb-ring-one" />
      <div className="orb-ring orb-ring-two" />
      {nodes.map((employee, index) => {
        const angle = (index / nodes.length) * Math.PI * 2
        const radius = index % 2 ? 112 : 82
        const left = 50 + Math.cos(angle) * (radius / 3.9)
        const top = 50 + Math.sin(angle) * (radius / 3.9)
        return (
          <div
            key={employee.employee_id}
            className="orb-node"
            style={{ left: `${left}%`, top: `${top}%`, animationDelay: `${index * 80}ms` }}
            title={employee.name}
          >
            {employee.name
              .split(' ')
              .map((part) => part[0])
              .join('')
              .slice(0, 2)}
          </div>
        )
      })}
    </div>
  )
}

export default function OverviewDashboard({ onNavigate }) {
  const now = useMemo(() => new Date(), [])
  const [domain, setDomain] = useState(null)
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const data = await fetchRosterDomain()
        if (!active) return
        setDomain(data)
        const year = now.getFullYear()
        const month = now.getMonth() + 1
        let monthly
        try {
          monthly = await fetchRoster(year, month)
        } catch {
          monthly = await generateRoster(year, month)
        }
        if (active) setRoster(monthly)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [now])

  const coverage = useMemo(() => {
    if (!roster?.coverage) return 0
    let covered = 0
    let required = 0
    Object.values(roster.coverage).forEach((day) => {
      Object.values(day).forEach((item) => {
        if (item.status !== 'CLOSED') {
          required += item.required
          covered += Math.min(item.actual, item.required)
        }
      })
    })
    return required ? Math.round((covered / required) * 100) : 100
  }, [roster])

  const scheduledShifts = useMemo(() => {
    if (!roster?.employee_schedule) return 0
    return Object.values(roster.employee_schedule).reduce(
      (total, schedule) => total + Object.values(schedule).filter((status) => status === 'WORK').length,
      0,
    )
  }, [roster])

  const employeesOnLeave = useMemo(() => {
    if (!domain?.employees) return 0
    return domain.employees.filter((employee) =>
      [...(employee.leaves || []), ...(employee.comp_offs || [])].some((date) =>
        date.startsWith(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`),
      ),
    ).length
  }, [domain, now])

  const upcomingHolidays = useMemo(() => {
    if (!domain?.holidays) return []
    const today = now.toISOString().slice(0, 10)
    return domain.holidays
      .filter((holiday) => holiday.date >= today)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 4)
  }, [domain, now])

  const chartData = useMemo(() => {
    if (!roster?.coverage) return []
    return Object.entries(roster.coverage).slice(0, 14).map(([date, day]) => {
      let required = 0
      let actual = 0
      Object.values(day).forEach((item) => {
        if (item.status !== 'CLOSED') {
          required += item.required
          actual += item.actual
        }
      })
      return {
        day: date.slice(-2),
        coverage: required ? Math.round((Math.min(actual, required) / required) * 100) : 100,
      }
    })
  }, [roster])

  const kpis = [
    { icon: Users, label: 'Total employees', value: domain?.employees.length ?? '—', detail: 'Across 4 operational pods', color: 'violet' },
    { icon: Layers3, label: 'Active brands', value: domain?.brands.filter((item) => item.active !== false).length ?? '—', detail: 'Brand portfolios connected', color: 'cyan' },
    { icon: ShieldCheck, label: 'Coverage', value: `${coverage}%`, detail: 'Mandatory process coverage', color: 'emerald' },
    { icon: CalendarDays, label: 'Scheduled shifts', value: scheduledShifts, detail: 'This active monthly roster', color: 'violet' },
    { icon: AlertTriangle, label: 'Active conflicts', value: roster?.conflicts?.length ?? 0, detail: 'Requires operations review', color: roster?.conflicts?.length ? 'red' : 'emerald' },
    { icon: Clock3, label: 'Employees on leave', value: employeesOnLeave, detail: 'Leave and comp-off entries', color: 'amber' },
  ]

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="page-heading">
        <div>
          <p className="eyebrow">Operations command center</p>
          <h1>Workforce overview</h1>
          <p>Live staffing, coverage, and operational readiness.</p>
        </div>
        <button onClick={() => onNavigate('monthly')} className="primary-button">
          Open monthly roster
          <ChevronRight size={16} />
        </button>
      </motion.div>

      {loading ? (
        <div className="glass-card h-52 animate-pulse rounded-2xl" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
            {kpis.map((kpi, index) => <KpiCard key={kpi.label} {...kpi} delay={index * 0.05} />)}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
            <section className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">14-day coverage</p>
                  <h2>Process availability trend</h2>
                </div>
                <span className="status-pill emerald">Live</span>
              </div>
              <div className="mt-5 h-64">
                {chartData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="coverageFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#22D3EE" stopOpacity={0.32} />
                          <stop offset="95%" stopColor="#22D3EE" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="day" stroke="#64748B" tickLine={false} axisLine={false} />
                      <YAxis stroke="#64748B" tickLine={false} axisLine={false} domain={[0, 100]} />
                      <Tooltip contentStyle={{ background: '#111827', border: '1px solid rgba(148,163,184,.18)', borderRadius: 12 }} />
                      <Area type="monotone" dataKey="coverage" stroke="#22D3EE" strokeWidth={2} fill="url(#coverageFill)" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="grid h-full place-items-center text-sm text-slate-500">Generate a monthly roster to view coverage.</p>
                )}
              </div>
            </section>

            <section className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="eyebrow">Team network</p>
                  <h2>Workforce topology</h2>
                </div>
                <span className="status-pill violet">{domain?.employees.length ?? 0} people</span>
              </div>
              <WorkforceOrb employees={domain?.employees ?? []} />
            </section>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <section className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <h2>Upcoming holidays</h2>
                <button className="text-xs text-cyan-300" onClick={() => onNavigate('management', 'holidays')}>Manage</button>
              </div>
              <div className="mt-4 space-y-2">
                {upcomingHolidays.length ? upcomingHolidays.map((holiday) => (
                  <div key={holiday.date} className="flex items-center justify-between rounded-xl border border-slate-700/60 bg-slate-950/30 px-4 py-3">
                    <div><p className="text-sm text-slate-200">{holiday.name}</p><p className="text-xs text-slate-500">{holiday.scope}</p></div>
                    <span className="text-xs text-slate-400">{holiday.date}</span>
                  </div>
                )) : <p className="text-sm text-slate-500">No upcoming holidays.</p>}
              </div>
            </section>

            <section className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <h2>Operational attention</h2>
                <button className="text-xs text-red-300" onClick={() => onNavigate('conflicts')}>View conflicts</button>
              </div>
              <div className="mt-4">
                {roster?.conflicts?.length ? (
                  <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
                    <p className="text-sm font-medium text-red-300">{roster.conflicts.length} issue(s) require review</p>
                    <p className="mt-1 text-xs text-slate-400">{roster.conflicts[0].message}</p>
                  </div>
                ) : (
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                    <p className="text-sm font-medium text-emerald-300">Operations are clear</p>
                    <p className="mt-1 text-xs text-slate-400">No mandatory conflicts in the active monthly roster.</p>
                  </div>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  )
}

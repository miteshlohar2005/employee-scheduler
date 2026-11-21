import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CalendarClock, CheckCircle2, RefreshCw } from 'lucide-react'
import { fetchRoster, fetchRosterDomain, generateRoster, validateRoster } from '../api'

export function LeaveAvailabilityView() {
  return (
    <div className="space-y-4">
      <div className="page-heading">
        <div><p className="eyebrow">Time and attendance</p><h1>Leave & availability</h1><p>Review planned leave, comp-offs, and unavailable dates.</p></div>
      </div>
      <LeaveAvailabilityPanel />
    </div>
  )
}

export function LeaveAvailabilityPanel() {
  const [domain, setDomain] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    fetchRosterDomain().then(setDomain).catch((err) => setError(err.message))
  }, [])
  const employees = domain?.employees || []
  return (
    <section className="glass-card overflow-hidden rounded-2xl">
      {error && <p className="m-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p>}
      <div className="overflow-x-auto">
        <table className="enterprise-table">
          <thead><tr><th>Employee</th><th>Pod</th><th>Leave</th><th>Comp-offs</th><th>Unavailable</th></tr></thead>
          <tbody>
            {employees.map((employee) => (
              <tr key={employee.employee_id}>
                <td><span className="employee-name">{employee.name}</span><span className="employee-id">{employee.employee_id}</span></td>
                <td>{employee.pod_id}</td>
                <td>{employee.leaves?.length ? employee.leaves.join(', ') : '—'}</td>
                <td>{employee.comp_offs?.length ? employee.comp_offs.join(', ') : '—'}</td>
                <td>{employee.availability?.length ? employee.availability.join(', ') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function ConflictCenter() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [roster, setRoster] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async (generate = false) => {
    setLoading(true)
    setError('')
    try {
      let data
      try {
        data = await fetchRoster(year, month)
      } catch {
        data = await generateRoster(year, month)
      }
      if (generate) data = await generateRoster(year, month)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [year, month])

  useEffect(() => { load(false) }, [load])

  const revalidate = async () => {
    setLoading(true)
    setError('')
    try {
      setRoster(await validateRoster(year, month))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const conflicts = roster?.conflicts || []

  return (
    <div className="space-y-5">
      <div className="page-heading">
        <div><p className="eyebrow">Mandatory constraint review</p><h1>Conflict center</h1><p>Unresolved staffing issues and actionable resolutions.</p></div>
        <div className="flex items-center gap-2">
          <input type="month" value={`${year}-${String(month).padStart(2, '0')}`} onChange={(event) => {
            const [nextYear, nextMonth] = event.target.value.split('-').map(Number)
            if (nextYear && nextMonth) { setYear(nextYear); setMonth(nextMonth) }
          }} className="enterprise-input" />
          <button onClick={revalidate} disabled={loading} className="secondary-button"><RefreshCw size={15} /> Revalidate</button>
        </div>
      </div>

      {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="glass-card rounded-2xl p-5"><p className="metric-label">Total conflicts</p><p className="metric-value">{conflicts.length}</p></div>
        <div className="glass-card rounded-2xl p-5"><p className="metric-label">Critical</p><p className="metric-value text-red-300">{conflicts.filter((item) => item.severity === 'critical').length}</p></div>
        <div className="glass-card rounded-2xl p-5"><p className="metric-label">Roster state</p><p className="metric-value text-base uppercase">{roster?.publish_status || 'Draft'}</p></div>
      </div>

      <section className="glass-card rounded-2xl p-5">
        {loading ? (
          <p className="text-sm text-slate-400">Loading conflict data...</p>
        ) : conflicts.length ? (
          <div className="space-y-3">
            {conflicts.map((conflict, index) => (
              <article key={`${conflict.type}-${conflict.date}-${index}`} className={`conflict-row ${conflict.severity === 'critical' ? 'critical' : 'warning'}`}>
                <div className="conflict-icon">{conflict.severity === 'critical' ? <AlertTriangle size={18} /> : <CalendarClock size={18} />}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-100">{conflict.type.replaceAll('_', ' ')}</span>
                    <span className="text-xs text-slate-500">{conflict.date || 'Month-wide'} · {conflict.brand_id || 'Brand'} · {conflict.process_id || 'Process'}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-300">{conflict.message}</p>
                  {conflict.resolution && <p className="mt-2 text-xs text-cyan-300">Resolution: {conflict.resolution}</p>}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="grid min-h-48 place-items-center text-center">
            <div><CheckCircle2 className="mx-auto text-emerald-400" size={34} /><p className="mt-3 text-sm font-medium text-slate-200">No active conflicts</p><p className="mt-1 text-xs text-slate-500">The selected roster satisfies current mandatory constraints.</p></div>
          </div>
        )}
      </section>
    </div>
  )
}

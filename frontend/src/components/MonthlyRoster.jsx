import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  changeRosterLeave,
  editRosterEntry,
  fetchRosterDomain,
  fetchRosterView,
  generateRoster,
  publishRoster,
  validateRoster,
} from '../api'

const STATUS_STYLES = {
  WORK: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  LEAVE: 'bg-rose-500/15 text-rose-300 ring-rose-500/30',
  COMP_OFF: 'bg-cyan-500/15 text-cyan-300 ring-cyan-500/30',
  UNAVAILABLE: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  HOLIDAY: 'bg-violet-500/15 text-violet-300 ring-violet-500/30',
  PREFERRED_WEEKLY_OFF: 'bg-slate-700 text-slate-300 ring-slate-600',
  OFF: 'bg-slate-900/60 text-slate-500 ring-slate-800',
}

function MonthlyRoster({ onAuthRequired }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [domain, setDomain] = useState(null)
  const [roster, setRoster] = useState(null)
  const [view, setView] = useState('company')
  const [filterId, setFilterId] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [edit, setEdit] = useState({ employee_id: '', process_id: '', date: '', action: 'add' })
  const [leave, setLeave] = useState({ employee_id: '', date: '', type: 'leave' })

  const load = useCallback(async (selectedYear = year, selectedMonth = month) => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchRosterView(selectedYear, selectedMonth, view, filterId || undefined)
      setRoster(data)
    } catch (err) {
      setRoster(null)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [year, month, view, filterId])

  useEffect(() => {
    fetchRosterDomain().then(setDomain).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    load(year, month)
  }, [year, month, view, filterId, load])

  const handleGenerate = async () => {
    if (!sessionStorage.getItem('roster_auth_token')) {
      setError('Sign-in required. Use Admin sign in before generating a roster.')
      onAuthRequired?.()
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await generateRoster(year, month)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleValidate = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await validateRoster(year, month)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handlePublish = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await publishRoster(year, month)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const submitEntryEdit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await editRosterEntry(year, month, edit)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const submitLeave = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await changeRosterLeave(year, month, leave)
      setRoster(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const days = useMemo(() => {
    if (!roster?.employee_schedule) return []
    const employeeSchedules = Object.values(roster.employee_schedule)
    if (employeeSchedules.length === 0) return []
    return Object.keys(employeeSchedules[0]).sort()
  }, [roster])

  const employees = useMemo(() => {
    if (!domain?.employees) return []
    return domain.employees.filter((employee) =>
      employee.name.toLowerCase().includes(search.toLowerCase()) ||
      employee.employee_id.toLowerCase().includes(search.toLowerCase())
    )
  }, [domain, search])

  const employeeNames = domain ? Object.fromEntries(domain.employees.map((item) => [item.employee_id, item.name])) : {}
  const visibleEmployeeIds = roster?.employee_schedule
    ? Object.keys(roster.employee_schedule)
    : employees.map((item) => item.employee_id)

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-400">Month
            <select value={month} onChange={(event) => setMonth(Number(event.target.value))} className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
              {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-400">Year
            <input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} className="mt-1 block w-28 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </label>
          <button onClick={handleGenerate} disabled={loading} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">Generate roster</button>
          <button onClick={handleValidate} disabled={loading || !roster} className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:border-indigo-500 disabled:opacity-50">Validate</button>
          <button onClick={handlePublish} disabled={loading || !roster} className="rounded-lg border border-emerald-700 px-4 py-2 text-sm text-emerald-300 hover:border-emerald-500 disabled:opacity-50">Publish</button>
          {roster?.publish_status && <span className="rounded-full border border-slate-700 px-3 py-1 text-xs uppercase tracking-wide">{roster.publish_status}</span>}
        </div>
      </section>

      {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p>}

      <section className="grid gap-4 xl:grid-cols-[220px_1fr]">
        <aside className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div>
            <label className="text-xs text-slate-400">Roster view</label>
            <select value={view} onChange={(event) => { setView(event.target.value); setFilterId('') }} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
              <option value="company">Company-wide</option>
              <option value="pod">Pod-wise</option>
              <option value="brand">Brand-wise</option>
              <option value="process">Process-wise</option>
              <option value="employee">Employee-wise</option>
            </select>
          </div>
          {view !== 'company' && domain && (
            <div>
              <label className="text-xs text-slate-400">Filter</label>
              <select value={filterId} onChange={(event) => setFilterId(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
                <option value="">Select...</option>
                {(view === 'pod' ? domain.pods : view === 'brand' ? domain.brands : view === 'process' ? domain.processes : domain.employees).map((item) => (
                  <option key={item.pod_id || item.brand_id || item.process_id || item.employee_id} value={item.pod_id || item.brand_id || item.process_id || item.employee_id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="text-xs text-slate-400">Search employee</label>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or ID" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </div>

          <form onSubmit={submitEntryEdit} className="space-y-2 border-t border-slate-800 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Edit entry</p>
            <select value={edit.employee_id} onChange={(event) => setEdit({ ...edit, employee_id: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs">
              <option value="">Employee</option>
              {domain?.employees.map((item) => <option key={item.employee_id} value={item.employee_id}>{item.name}</option>)}
            </select>
            <select value={edit.process_id} onChange={(event) => setEdit({ ...edit, process_id: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs">
              <option value="">Process</option>
              {domain?.processes.map((item) => <option key={item.process_id} value={item.process_id}>{item.name}</option>)}
            </select>
            <input type="date" value={edit.date} onChange={(event) => setEdit({ ...edit, date: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs" />
            <select value={edit.action} onChange={(event) => setEdit({ ...edit, action: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs">
              <option value="add">Add work entry</option>
              <option value="remove">Remove work entry</option>
            </select>
            <button className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium">Apply and revalidate</button>
          </form>

          <form onSubmit={submitLeave} className="space-y-2 border-t border-slate-800 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Add approved change</p>
            <select value={leave.employee_id} onChange={(event) => setLeave({ ...leave, employee_id: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs">
              <option value="">Employee</option>
              {domain?.employees.map((item) => <option key={item.employee_id} value={item.employee_id}>{item.name}</option>)}
            </select>
            <input type="date" value={leave.date} onChange={(event) => setLeave({ ...leave, date: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs" />
            <select value={leave.type} onChange={(event) => setLeave({ ...leave, type: event.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs">
              <option value="leave">Leave</option>
              <option value="comp_off">Comp-off</option>
              <option value="availability">Unavailable</option>
            </select>
            <button className="w-full rounded-lg border border-cyan-700 px-3 py-2 text-xs text-cyan-300">Apply change</button>
          </form>
        </aside>

        <div className="min-w-0 space-y-4">
          {loading && <p className="rounded-lg border border-slate-800 px-4 py-3 text-sm text-slate-400">Loading roster...</p>}
          {roster && (
            <>
              <div className="overflow-x-auto rounded-2xl border border-slate-800">
                <table className="min-w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-900">
                      <th className="sticky left-0 z-10 min-w-44 border-b border-slate-800 bg-slate-950 px-3 py-3 text-left">Employee</th>
                      {days.map((day) => <th key={day} className="min-w-20 border-b border-slate-800 px-2 py-3 text-center">{day.slice(-2)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {visibleEmployeeIds
                      .filter((employeeId) => employeeNames[employeeId]?.toLowerCase().includes(search.toLowerCase()) || employeeId.toLowerCase().includes(search.toLowerCase()))
                      .map((employeeId) => (
                        <tr key={employeeId} className="border-b border-slate-800/70">
                          <td className="sticky left-0 z-10 bg-slate-950 px-3 py-2">
                            <span className="font-medium">{employeeNames[employeeId] || employeeId}</span>
                            <span className="ml-2 text-slate-500">{employeeId}</span>
                          </td>
                          {days.map((day) => {
                            const status = roster.employee_schedule?.[employeeId]?.[day] || 'OFF'
                            return (
                              <td key={day} className="px-2 py-2 text-center">
                                <span className={`inline-flex min-w-12 justify-center rounded-md px-1.5 py-1 ring-1 ring-inset ${STATUS_STYLES[status] || STATUS_STYLES.OFF}`}>
                                  {status === 'PREFERRED_WEEKLY_OFF' ? 'OFF' : status.replace('_', ' ')}
                                </span>
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded-2xl border border-slate-800 p-4">
                <h3 className="text-sm font-semibold">Conflicts and validation</h3>
                {roster.conflicts?.length ? (
                  <div className="mt-3 space-y-2">
                    {roster.conflicts.slice(0, 50).map((conflict, index) => (
                      <div key={`${conflict.type}-${conflict.date}-${index}`} className={`rounded-lg border px-3 py-2 text-xs ${conflict.severity === 'critical' ? 'border-red-500/30 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'}`}>
                        <p className="font-medium">{conflict.date || 'Month-wide'} · {conflict.brand_id || 'Brand'} · {conflict.process_id || 'Process'}</p>
                        <p className="mt-1 text-slate-300">{conflict.message}</p>
                        {conflict.resolution && <p className="mt-1 text-cyan-300">Resolution: {conflict.resolution}</p>}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-emerald-300">No conflicts detected.</p>
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

export default MonthlyRoster

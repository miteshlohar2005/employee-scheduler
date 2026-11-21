import { useEffect, useState } from 'react'
import {
  createManagement,
  deleteAssignment,
  deleteManagement,
  fetchRosterDomain,
  updateManagement,
} from '../api'

const EMPTY_FORMS = {
  employees: { employee_id: '', name: '', pod_id: '', employment_type: 'full_time', weekly_off: 6, availability: '', leaves: '', comp_offs: '' },
  brands: { brand_id: '', name: '', active: true },
  processes: { process_id: '', brand_id: '', name: '', calendar: '365', minimum_staff: 1, active: true },
  pods: { pod_id: '', name: '', lead_employee_id: '' },
  holidays: { date: '', name: '', scope: 'India' },
  assignments: { employee_id: '', brand_id: '', process_id: '', active: true },
}

function Management({ initialResource = 'employees' }) {
  const [domain, setDomain] = useState(null)
  const [resource, setResource] = useState(initialResource)
  const [form, setForm] = useState(EMPTY_FORMS.employees)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setError('')
    try {
      setDomain(await fetchRosterDomain())
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    setForm(EMPTY_FORMS[resource])
    setEditing(null)
  }, [resource])

  const updateField = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      let payload = { ...form }
      if (resource === 'employees') {
        payload.weekly_off = Number(payload.weekly_off)
        payload.availability = payload.availability ? payload.availability.split(',').map((item) => item.trim()).filter(Boolean) : []
        payload.leaves = payload.leaves ? payload.leaves.split(',').map((item) => item.trim()).filter(Boolean) : []
        payload.comp_offs = payload.comp_offs ? payload.comp_offs.split(',').map((item) => item.trim()).filter(Boolean) : []
      }
      if (resource === 'processes') payload.minimum_staff = Number(payload.minimum_staff)
      if (editing) {
        const id = editing
        await updateManagement(resource, id, payload)
      } else if (resource === 'assignments') {
        await createManagement(resource, payload)
      } else {
        await createManagement(resource, payload)
      }
      setForm(EMPTY_FORMS[resource])
      setEditing(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const beginEdit = (item) => {
    setEditing(
      resource === 'employees' ? item.employee_id :
      resource === 'brands' ? item.brand_id :
      resource === 'processes' ? item.process_id :
      resource === 'pods' ? item.pod_id :
      item.date,
    )
    if (resource === 'employees') {
      setForm({
        employee_id: item.employee_id,
        name: item.name,
        pod_id: item.pod_id,
        employment_type: item.employment_type,
        weekly_off: item.weekly_off,
        availability: (item.availability || []).join(', '),
        leaves: (item.leaves || []).join(', '),
        comp_offs: (item.comp_offs || []).join(', '),
      })
    } else if (resource === 'processes') {
      setForm({
        process_id: item.process_id,
        brand_id: item.brand_id,
        name: item.name,
        calendar: item.calendar,
        minimum_staff: item.minimum_staff,
        active: item.active,
      })
    } else {
      setForm({ ...item })
    }
  }

  const removeItem = async (item) => {
    const label = item.name || item.employee_id || item.process_id || item.date
    if (!window.confirm(`Delete ${label}? This action cannot be undone.`)) return
    setBusy(true)
    setError('')
    try {
      if (resource === 'assignments') {
        await deleteAssignment(item.employee_id, item.brand_id, item.process_id)
      } else {
        const id = resource === 'employees' ? item.employee_id :
          resource === 'brands' ? item.brand_id :
          resource === 'processes' ? item.process_id :
          resource === 'pods' ? item.pod_id :
          item.date
        await deleteManagement(resource, id)
      }
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const employeesById = domain ? Object.fromEntries(domain.employees.map((item) => [item.employee_id, item.name])) : {}
  const brandsById = domain ? Object.fromEntries(domain.brands.map((item) => [item.brand_id, item.name])) : {}
  const processesById = domain ? Object.fromEntries(domain.processes.map((item) => [item.process_id, item.name])) : {}
  const list = domain
    ? resource === 'employees' ? domain.employees
      : resource === 'brands' ? domain.brands
        : resource === 'processes' ? domain.processes
          : resource === 'pods' ? domain.pods
            : resource === 'holidays' ? domain.holidays
              : domain.assignments
    : []

  return (
    <section className="grid gap-5 lg:grid-cols-[220px_1fr]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/50 p-3">
        {['employees', 'brands', 'processes', 'pods', 'holidays', 'assignments'].map((item) => (
          <button
            key={item}
            onClick={() => setResource(item)}
            className={`mb-1 w-full rounded-lg px-3 py-2 text-left text-sm capitalize ${resource === item ? 'bg-indigo-600/20 text-indigo-300' : 'text-slate-400 hover:bg-slate-800/60'}`}
          >
            {item}
          </button>
        ))}
      </aside>

      <div className="space-y-4">
        {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">{error}</p>}

        {resource !== 'assignments' && (
          <form onSubmit={submit} className="grid gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {resource === 'employees' && (
              <>
                <input placeholder="Employee ID" value={form.employee_id} disabled={Boolean(editing)} onChange={(event) => updateField('employee_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required />
                <input placeholder="Name" value={form.name} onChange={(event) => updateField('name', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required />
                <select value={form.pod_id} onChange={(event) => updateField('pod_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required>
                  <option value="">Pod</option>{domain?.pods.map((item) => <option key={item.pod_id} value={item.pod_id}>{item.name}</option>)}
                </select>
                <select value={form.employment_type} onChange={(event) => updateField('employment_type', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
                  <option value="full_time">Full-time</option><option value="part_time">Part-time</option>
                </select>
                <input type="number" min="0" max="6" value={form.weekly_off} onChange={(event) => updateField('weekly_off', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" title="0 Monday to 6 Sunday" />
                <input placeholder="Availability YYYY-MM-DD, ..." value={form.availability} onChange={(event) => updateField('availability', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
                <input placeholder="Leaves YYYY-MM-DD, ..." value={form.leaves} onChange={(event) => updateField('leaves', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
                <input placeholder="Comp-offs YYYY-MM-DD, ..." value={form.comp_offs} onChange={(event) => updateField('comp_offs', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
              </>
            )}
            {resource === 'brands' && (
              <><input placeholder="Brand ID" value={form.brand_id} disabled={Boolean(editing)} onChange={(event) => updateField('brand_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /><input placeholder="Name" value={form.name} onChange={(event) => updateField('name', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /></>
            )}
            {resource === 'processes' && (
              <>
                <input placeholder="Process ID" value={form.process_id} disabled={Boolean(editing)} onChange={(event) => updateField('process_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required />
                <select value={form.brand_id} onChange={(event) => updateField('brand_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required><option value="">Brand</option>{domain?.brands.map((item) => <option key={item.brand_id} value={item.brand_id}>{item.name}</option>)}</select>
                <input placeholder="Process name" value={form.name} onChange={(event) => updateField('name', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required />
                <select value={form.calendar} onChange={(event) => updateField('calendar', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"><option value="365">365 days</option><option value="weekdays">Weekdays only</option><option value="sunday_holiday_off">Sunday and holiday off</option></select>
                <input type="number" min="1" value={form.minimum_staff} onChange={(event) => updateField('minimum_staff', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
              </>
            )}
            {resource === 'pods' && (
              <><input placeholder="Pod ID" value={form.pod_id} disabled={Boolean(editing)} onChange={(event) => updateField('pod_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /><input placeholder="Name" value={form.name} onChange={(event) => updateField('name', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /><select value={form.lead_employee_id || ''} onChange={(event) => updateField('lead_employee_id', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"><option value="">Pod lead</option>{domain?.employees.map((item) => <option key={item.employee_id} value={item.employee_id}>{item.name}</option>)}</select></>
            )}
            {resource === 'holidays' && (
              <><input type="date" value={form.date} disabled={Boolean(editing)} onChange={(event) => updateField('date', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /><input placeholder="Holiday name" value={form.name} onChange={(event) => updateField('name', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required /><input placeholder="Scope" value={form.scope} onChange={(event) => updateField('scope', event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" /></>
            )}
            <div className="flex items-end gap-2">
              <button disabled={busy} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm">{editing ? 'Save changes' : 'Create'}</button>
              {editing && <button type="button" onClick={() => { setEditing(null); setForm(EMPTY_FORMS[resource]) }} className="rounded-lg border border-slate-700 px-4 py-2 text-sm">Cancel</button>}
            </div>
          </form>
        )}

        {resource === 'assignments' && (
          <AssignmentForm domain={domain} onSaved={load} />
        )}

        <div className="overflow-x-auto rounded-2xl border border-slate-800">
          <table className="min-w-full text-sm">
            <thead><tr className="border-b border-slate-800 text-left text-slate-400"><th className="px-4 py-3">Record</th><th className="px-4 py-3">Details</th><th className="px-4 py-3">Actions</th></tr></thead>
            <tbody>
              {list.map((item, index) => (
                <tr key={item.employee_id || item.brand_id || item.process_id || item.pod_id || item.date || index} className="border-b border-slate-800/70">
                  <td className="px-4 py-3 font-medium">{item.name || item.employee_id || item.process_id || item.date}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {resource === 'employees' && `${item.employee_id} · Pod ${item.pod_id} · ${item.employment_type} · off ${item.weekly_off}`}
                    {resource === 'brands' && item.brand_id}
                    {resource === 'processes' && `${brandsById[item.brand_id] || item.brand_id} · ${item.calendar} · min ${item.minimum_staff}`}
                    {resource === 'pods' && `Lead: ${employeesById[item.lead_employee_id] || item.lead_employee_id || 'Unassigned'}`}
                    {resource === 'holidays' && `${item.scope || ''}`}
                    {resource === 'assignments' && `${employeesById[item.employee_id]} → ${brandsById[item.brand_id]} / ${processesById[item.process_id]}`}
                  </td>
                  <td className="px-4 py-3">
                    {resource !== 'assignments' && <button onClick={() => beginEdit(item)} className="mr-3 text-indigo-300">Edit</button>}
                    <button onClick={() => removeItem(item)} className="text-red-300">Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

function AssignmentForm({ domain, onSaved }) {
  const [form, setForm] = useState({ employee_id: '', brand_id: '', process_id: '' })
  const [error, setError] = useState('')
  const submit = async (event) => {
    event.preventDefault()
    setError('')
    try {
      await createManagement('assignments', form)
      setForm({ employee_id: '', brand_id: '', process_id: '' })
      await onSaved()
    } catch (err) {
      setError(err.message)
    }
  }
  const filteredProcesses = domain?.processes.filter((item) => !form.brand_id || item.brand_id === form.brand_id) || []
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-4 sm:grid-cols-4">
      {error && <p className="sm:col-span-4 text-sm text-red-300">{error}</p>}
      <select value={form.employee_id} onChange={(event) => setForm({ ...form, employee_id: event.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required><option value="">Employee</option>{domain?.employees.map((item) => <option key={item.employee_id} value={item.employee_id}>{item.name}</option>)}</select>
      <select value={form.brand_id} onChange={(event) => setForm({ ...form, brand_id: event.target.value, process_id: '' })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required><option value="">Brand</option>{domain?.brands.map((item) => <option key={item.brand_id} value={item.brand_id}>{item.name}</option>)}</select>
      <select value={form.process_id} onChange={(event) => setForm({ ...form, process_id: event.target.value })} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" required><option value="">Process</option>{filteredProcesses.map((item) => <option key={item.process_id} value={item.process_id}>{item.name}</option>)}</select>
      <button className="rounded-lg bg-indigo-600 px-4 py-2 text-sm">Create assignment</button>
    </form>
  )
}

export default Management

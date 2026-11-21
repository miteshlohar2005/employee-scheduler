const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' && window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : 'http://localhost:8000')

function authHeaders(extra = {}) {
  const token = sessionStorage.getItem('roster_auth_token')
  return token
    ? { Authorization: `Bearer ${token}`, ...extra }
    : { ...extra }
}

async function parseJsonOrThrow(response) {
  let data = null
  try {
    data = await response.json()
  } catch {
    // no JSON body - fall through to the status-based error below
  }

  if (!response.ok) {
    throw new Error(formatApiError(data, response.status))
  }

  return data
}

export function formatApiError(data, status = 0) {
  if (typeof data === 'string' && data.trim()) return data.trim()

  const errors = Array.isArray(data?.errors) ? data.errors : []
  if (errors.length) {
    const first = errors[0]
    if (typeof first === 'string') return first
    if (first?.msg) return first.msg
  }

  const detail = data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        const location = Array.isArray(item?.loc) ? item.loc.join('.') : null
        const message = item?.msg || item?.message
        return [location, message].filter(Boolean).join(': ')
      })
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  if (detail && typeof detail === 'object') {
    const conflicts = Array.isArray(detail.conflicts) ? detail.conflicts : []
    const mandatory = conflicts.filter((conflict) =>
      conflict?.constraint === 'mandatory' || conflict?.severity === 'critical'
    )
    if (mandatory.length) {
      const conflict = mandatory[0]
      const employee = conflict.employee_id ? ` ${conflict.employee_id}` : ''
      const process = conflict.process_id ? ` / ${conflict.process_id}` : ''
      const date = conflict.date ? ` on ${conflict.date}` : ''
      const count = `${mandatory.length} mandatory conflict${mandatory.length === 1 ? '' : 's'}`
      const base = detail.message || 'Cannot publish the roster'
      return `${base.replace(/[.!]+$/, '')}. ${count} remain${mandatory.length === 1 ? 's' : ''}:${employee}${process}${date}.`
    }
    if (detail.message) return detail.message

    const validationStatus = data?.status || detail.status
    if (validationStatus === 'INFEASIBLE') {
      const count = Array.isArray(detail.conflicts)
        ? detail.conflicts.filter((conflict) => conflict?.constraint === 'mandatory').length
        : 0
      return `Publishing is blocked by ${count} mandatory conflict${count === 1 ? '' : 's'}.`
    }
  }
  if (data?.message) return data.message
  return `Request failed with status ${status || 'unknown'}`
}

export async function uploadExcel(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
    headers: authHeaders(),
  })
  return parseJsonOrThrow(response)
}

export async function fetchStores() {
  const response = await fetch(`${API_BASE_URL}/stores`)
  return parseJsonOrThrow(response)
}

export async function fetchSchedule(storeId) {
  const response = await fetch(`${API_BASE_URL}/schedule/${encodeURIComponent(storeId)}`)
  return parseJsonOrThrow(response)
}

export async function loginRoster(username, password) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  return parseJsonOrThrow(response)
}

export async function logoutRoster() {
  const response = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (response.ok) sessionStorage.removeItem('roster_auth_token')
  return parseJsonOrThrow(response)
}

async function jsonRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...(options.headers || {}),
      },
    })
  } catch {
    throw new Error(
      `Cannot reach the backend at ${API_BASE_URL}. Check that the API server is running.`,
    )
  }
  if (response.status === 401) {
    throw new Error('Sign-in required. Use Admin sign in, then generate or publish the roster.')
  }
  return parseJsonOrThrow(response)
}

export const fetchRosterDomain = () => fetch(`${API_BASE_URL}/roster/domain`).then(parseJsonOrThrow)
export const generateRoster = (year, month) => {
  if (!sessionStorage.getItem('roster_auth_token')) {
    throw new Error('Sign-in required. Use Admin sign in before generating a roster.')
  }
  return jsonRequest('/roster/generate', { method: 'POST', body: JSON.stringify({ year, month }) })
}
export const fetchRoster = (year, month) =>
  fetch(`${API_BASE_URL}/roster/${year}/${month}`).then(parseJsonOrThrow)
export const validateRoster = (year, month) =>
  jsonRequest(`/roster/${year}/${month}/validate`, { method: 'POST' })
export const publishRoster = (year, month) =>
  jsonRequest(`/roster/${year}/${month}/publish`, { method: 'POST' })
export const changeRosterLeave = (year, month, payload) =>
  jsonRequest(`/roster/${year}/${month}/leave`, { method: 'POST', body: JSON.stringify(payload) })
export const removeRosterLeave = (year, month, payload) =>
  jsonRequest(
    `/roster/${year}/${month}/leave?employee_id=${encodeURIComponent(payload.employee_id)}&date=${encodeURIComponent(payload.date)}&type=${encodeURIComponent(payload.type)}`,
    { method: 'DELETE' },
  )
export const editRosterEntry = (year, month, payload) =>
  jsonRequest(`/roster/${year}/${month}/entry`, { method: 'PUT', body: JSON.stringify(payload) })
export const changeRosterAssignment = (year, month, payload) =>
  jsonRequest(`/roster/${year}/${month}/assignment`, { method: 'PUT', body: JSON.stringify(payload) })
export const fetchRosterView = (year, month, view, filterId) => {
  const query = filterId ? `?filter_id=${encodeURIComponent(filterId)}` : ''
  return fetch(`${API_BASE_URL}/roster/${year}/${month}/view/${view}${query}`).then(parseJsonOrThrow)
}

export const createManagement = (resource, payload) =>
  jsonRequest(`/management/${resource}`, { method: 'POST', body: JSON.stringify(payload) })
export const updateManagement = (resource, id, payload) =>
  jsonRequest(`/management/${resource}/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(payload) })
export const deleteManagement = (resource, id, query = '') =>
  jsonRequest(`/management/${resource}/${encodeURIComponent(id)}${query}`, { method: 'DELETE' })
export const deleteAssignment = (employeeId, brandId, processId) =>
  jsonRequest(
    `/management/assignments?employee_id=${encodeURIComponent(employeeId)}&brand_id=${encodeURIComponent(brandId)}&process_id=${encodeURIComponent(processId)}`,
    { method: 'DELETE' },
  )

const BASE = import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL.replace(/\/$/, '') : ''

// ── Auth & Token Storage ──

export function getAuthToken() {
  return localStorage.getItem('soc_access_token') || null
}

export function setAuthSession(token, user, profile, organization) {
  if (token) localStorage.setItem('soc_access_token', token)
  else localStorage.removeItem('soc_access_token')

  if (user) localStorage.setItem('soc_user', JSON.stringify(user))
  else localStorage.removeItem('soc_user')

  if (profile) localStorage.setItem('soc_profile', JSON.stringify(profile))
  else localStorage.removeItem('soc_profile')

  if (organization) localStorage.setItem('soc_org', JSON.stringify(organization))
  else localStorage.removeItem('soc_org')
}

export function clearAuthSession() {
  localStorage.removeItem('soc_access_token')
  localStorage.removeItem('soc_user')
  localStorage.removeItem('soc_profile')
  localStorage.removeItem('soc_org')
}

function authHeaders(headers = {}) {
  const token = getAuthToken()
  const h = { ...headers }
  if (token) {
    h['Authorization'] = `Bearer ${token}`
  }
  return h
}

// ── Auth API ──

export async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Login failed: ${res.status}`)
  }
  return res.json()
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get profile: ${res.status}`)
  return res.json()
}

export async function getOrganizations() {
  const res = await fetch(`${BASE}/organizations`)
  if (!res.ok) throw new Error(`Failed to get organizations: ${res.status}`)
  return res.json()
}

// ── Live Feed Generation ──
// POST /alerts/generate/start uses QUERY parameters (not body)

export async function startLiveFeed(duration = 120, interval = 5, poisonRatio = 0.15, orgId = null) {
  const params = new URLSearchParams({
    duration_seconds: String(duration),
    interval_seconds: String(interval),
    poison_ratio: String(poisonRatio),
  })
  if (orgId && orgId !== 'ALL') {
    params.set('org_id', orgId)
  }
  const res = await fetch(`${BASE}/alerts/generate/start?${params}`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to start live feed: ${res.status}`)
  }
  return res.json()
}

export async function getLiveFeedStatus() {
  const res = await fetch(`${BASE}/alerts/generate/status`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get status: ${res.status}`)
  return res.json()
}

export async function stopLiveFeed() {
  const res = await fetch(`${BASE}/alerts/generate/stop`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to stop: ${res.status}`)
  return res.json()
}

// ── Alerts ──

export async function getAlerts(limit = 50, status = null, orgId = null) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  if (orgId && orgId !== 'ALL') params.set('org_id', orgId)
  const res = await fetch(`${BASE}/alerts/?${params}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get alerts: ${res.status}`)
  return res.json()
}

export async function ingestAlert(alertData) {
  const res = await fetch(`${BASE}/alerts/`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(alertData),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to ingest alert: ${res.status}`)
  }
  return res.json()
}

// ── Firewall Flags ──

export async function getFirewallFlags(alertId = null, orgId = null) {
  const params = new URLSearchParams()
  if (alertId) params.set('alert_id', alertId)
  if (orgId && orgId !== 'ALL') params.set('org_id', orgId)
  const q = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/alerts/firewall-flags${q}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get firewall flags: ${res.status}`)
  return res.json()
}

// ── Settings / Mode ──

export async function getMode() {
  const res = await fetch(`${BASE}/settings/mode`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get mode: ${res.status}`)
  return res.json()
}

export async function setMode(mode) {
  const res = await fetch(`${BASE}/settings/mode`, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error(`Failed to set mode: ${res.status}`)
  return res.json()
}

// ── Cases ──

export async function getCases(limit = 100, status = null, orgId = null) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  if (orgId && orgId !== 'ALL') params.set('org_id', orgId)
  const res = await fetch(`${BASE}/cases/?${params}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get cases: ${res.status}`)
  return res.json()
}

export async function getCase(caseId) {
  const res = await fetch(`${BASE}/cases/${caseId}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get case: ${res.status}`)
  return res.json()
}

// ── Memory ──

export async function getMemoryRecords({ record_type = null, alert_type = null, limit = 100 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (record_type) params.set('record_type', record_type)
  if (alert_type) params.set('alert_type', alert_type)
  const res = await fetch(`${BASE}/memory/records?${params}`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get memory records: ${res.status}`)
  return res.json()
}

export async function submitAnalystDecision(caseId, { decision, analyst_action, analyst_reasoning }) {
  const res = await fetch(`${BASE}/cases/${caseId}/decision`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      decision,
      analyst_action,
      analyst_reasoning,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to submit decision: ${res.status}`)
  }
  return res.json()
}

// ── Dynamic Backend Target Resolution ──
// Priority:
// 1. Manually saved in localStorage ('soc_backend_url') — allows 1-click in-browser configuration
// 2. Build-time environment variable ('VITE_API_URL') — baked by Vercel/Vite
// 3. Fallback to empty string '' (which uses Vite local proxy)

export function getBaseUrl() {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('soc_backend_url')
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/$/, '')
    }
  }
  if (import.meta.env.VITE_API_URL && import.meta.env.VITE_API_URL.trim()) {
    return import.meta.env.VITE_API_URL.trim().replace(/\/$/, '')
  }
  // Production fallback: If running on Vercel or any cloud domain, automatically default to the live Render backend
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return 'https://autonomouss-soc-analyst.onrender.com'
  }
  return ''
}

export function setCustomBackendUrl(url) {
  if (typeof window !== 'undefined') {
    if (url && url.trim()) {
      localStorage.setItem('soc_backend_url', url.trim().replace(/\/$/, ''))
    } else {
      localStorage.removeItem('soc_backend_url')
    }
  }
}

export function endpoint(path) {
  const base = getBaseUrl()
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  return `${base}${cleanPath}`
}

export async function testBackendHealth(targetUrl = null) {
  const base = (targetUrl !== null ? targetUrl : getBaseUrl()).replace(/\/$/, '')
  const url = `${base}/health`
  const res = await fetch(url, { method: 'GET' })
  if (!res.ok) throw new Error(`Health check returned HTTP ${res.status}`)
  return res.json()
}

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
  const url = endpoint('/auth/login')
  const base = getBaseUrl()

  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  } catch (netErr) {
    throw new Error(`Cannot reach backend at ${url}. Check your backend URL or internet connection. (${netErr.message})`)
  }

  if (!res.ok) {
    if (res.status === 405) {
      if (!base) {
        throw new Error(
          'Login failed (405): VITE_API_URL is not set or not baked into this Vercel build. Click "Configure Backend URL" below to enter your backend URL directly.'
        )
      }
      throw new Error(
        `Login failed (405 Method Not Allowed at ${url}). Check that the backend URL is https:// and does not redirect.`
      )
    }
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Login failed: ${res.status}`)
  }
  return res.json()
}

export async function getMe() {
  const res = await fetch(endpoint('/auth/me'), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get profile: ${res.status}`)
  return res.json()
}

export async function getOrganizations() {
  const res = await fetch(endpoint('/organizations'))
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
  const res = await fetch(endpoint(`/alerts/generate/start?${params}`), {
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
  const res = await fetch(endpoint('/alerts/generate/status'), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get status: ${res.status}`)
  return res.json()
}

export async function stopLiveFeed() {
  const res = await fetch(endpoint('/alerts/generate/stop'), {
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
  const res = await fetch(endpoint(`/alerts/?${params}`), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get alerts: ${res.status}`)
  return res.json()
}

export async function ingestAlert(alertData) {
  const res = await fetch(endpoint('/alerts/'), {
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
  const res = await fetch(endpoint(`/alerts/firewall-flags${q}`), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get firewall flags: ${res.status}`)
  return res.json()
}

// ── Settings / Mode ──

export async function getMode() {
  const res = await fetch(endpoint('/settings/mode'), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get mode: ${res.status}`)
  return res.json()
}

export async function setMode(mode) {
  const res = await fetch(endpoint('/settings/mode'), {
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
  const res = await fetch(endpoint(`/cases/?${params}`), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get cases: ${res.status}`)
  return res.json()
}

export async function getCase(caseId) {
  const res = await fetch(endpoint(`/cases/${caseId}`), {
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
  const res = await fetch(endpoint(`/memory/records?${params}`), {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Failed to get memory records: ${res.status}`)
  return res.json()
}

export async function submitAnalystDecision(caseId, { decision, analyst_action, analyst_reasoning }) {
  const res = await fetch(endpoint(`/cases/${caseId}/decision`), {
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

const BASE = ''

// ── Live Feed Generation ──
// POST /alerts/generate/start uses QUERY parameters (not body)

export async function startLiveFeed(duration = 120, interval = 5, poisonRatio = 0.15) {
  const params = new URLSearchParams({
    duration_seconds: String(duration),
    interval_seconds: String(interval),
    poison_ratio: String(poisonRatio),
  })
  const res = await fetch(`${BASE}/alerts/generate/start?${params}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to start live feed: ${res.status}`)
  }
  return res.json()
}

export async function getLiveFeedStatus() {
  const res = await fetch(`${BASE}/alerts/generate/status`)
  if (!res.ok) throw new Error(`Failed to get status: ${res.status}`)
  return res.json()
}

export async function stopLiveFeed() {
  const res = await fetch(`${BASE}/alerts/generate/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to stop: ${res.status}`)
  return res.json()
}

// ── Alerts ──

export async function getAlerts(limit = 50, status = null) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  const res = await fetch(`${BASE}/alerts/?${params}`)
  if (!res.ok) throw new Error(`Failed to get alerts: ${res.status}`)
  return res.json()
}

// ── Firewall Flags ──

export async function getFirewallFlags(alertId) {
  const params = alertId ? `?alert_id=${alertId}` : ''
  const res = await fetch(`${BASE}/alerts/firewall-flags${params}`)
  if (!res.ok) throw new Error(`Failed to get firewall flags: ${res.status}`)
  return res.json()
}

// ── Settings / Mode ──

export async function getMode() {
  const res = await fetch(`${BASE}/settings/mode`)
  if (!res.ok) throw new Error(`Failed to get mode: ${res.status}`)
  return res.json()
}

export async function setMode(mode) {
  const res = await fetch(`${BASE}/settings/mode`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error(`Failed to set mode: ${res.status}`)
  return res.json()
}

// ── Cases ──

export async function getCase(caseId) {
  const res = await fetch(`${BASE}/cases/${caseId}`)
  if (!res.ok) throw new Error(`Failed to get case: ${res.status}`)
  return res.json()
}

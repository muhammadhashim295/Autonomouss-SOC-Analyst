const BASE_URL = '' // Vite proxy handles routing to backend

export async function startLiveFeed(duration = 120, interval = 5, poisonRatio = 0.15) {
  const res = await fetch(`${BASE_URL}/alerts/generate/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ duration, interval, poison_ratio: poisonRatio }),
  })
  if (!res.ok) throw new Error(`Failed to start live feed: ${res.status}`)
  return res.json()
}

export async function getLiveFeedStatus() {
  const res = await fetch(`${BASE_URL}/alerts/generate/status`)
  if (!res.ok) throw new Error(`Failed to get live feed status: ${res.status}`)
  return res.json()
}

export async function stopLiveFeed() {
  const res = await fetch(`${BASE_URL}/alerts/generate/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to stop live feed: ${res.status}`)
  return res.json()
}

export async function getAlerts(limit = 50, status = null) {
  const params = new URLSearchParams({ limit: limit.toString() })
  if (status) params.append('status', status)
  const res = await fetch(`${BASE_URL}/alerts/?${params}`)
  if (!res.ok) throw new Error(`Failed to fetch alerts: ${res.status}`)
  return res.json()
}

export async function getFirewallFlags(alertId) {
  const res = await fetch(`${BASE_URL}/alerts/firewall-flags?alert_id=${alertId}`)
  if (!res.ok) throw new Error(`Failed to fetch firewall flags: ${res.status}`)
  return res.json()
}

export async function getCaseDetail(caseId) {
  const res = await fetch(`${BASE_URL}/cases/${caseId}`)
  if (!res.ok) throw new Error(`Failed to fetch case: ${res.status}`)
  return res.json()
}

export async function getMode() {
  const res = await fetch(`${BASE_URL}/settings/mode`)
  if (!res.ok) throw new Error(`Failed to fetch mode: ${res.status}`)
  return res.json()
}

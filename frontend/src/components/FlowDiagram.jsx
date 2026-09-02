/**
 * Visual flow diagram showing pipeline stages as connected nodes.
 * Each node lights up as SSE events arrive.
 * 
 * @param {object} stages - Stage statuses: { liveEnv, firewall, primary, secondary, action, db }
 * @param {array|null} firewallFlags - Firewall flags array (null = not loaded, [] = clean, [...] = flagged)
 */
export default function FlowDiagram({ stages, firewallFlags }) {
  const stageConfig = {
    liveEnv: { label: "Live Environment", icon: "🌐" },
    firewall: { label: "Firewall", icon: "🛡️" },
    primary: { label: "Primary Agent", icon: "🤖" },
    secondary: { label: "Secondary Agent", icon: "🔍" },
    action: { label: "Response Action", icon: "⚡" },
    db: { label: "Documented in DB", icon: "💾" },
  }

  const statusColors = {
    pending: 'bg-gray-100 border-gray-300 text-gray-400',
    active: 'bg-blue-50 border-blue-400 text-blue-800',
    complete: 'bg-green-50 border-green-400 text-green-800',
    flagged: 'bg-orange-50 border-orange-400 text-orange-800',
    error: 'bg-red-50 border-red-400 text-red-800',
  }

  const getStatus = (stageName) => {
    return stages[stageName] || 'pending'
  }

  const getFirewallBadge = () => {
    if (firewallFlags === null) {
      return { text: 'Checking...', className: 'bg-gray-200 text-gray-600' }
    }
    if (firewallFlags.length === 0) {
      return { text: '✓ Clean', className: 'bg-green-200 text-green-800' }
    }
    return { text: `⚠ ${firewallFlags.length} flag(s)`, className: 'bg-orange-200 text-orange-800' }
  }

  const firewallBadge = getFirewallBadge()

  return (
    <div className="flex items-center justify-between gap-2 p-6 bg-white rounded-lg shadow">
      {Object.entries(stageConfig).map(([key, config], idx) => {
        const status = getStatus(key)
        const isFirewall = key === 'firewall'

        return (
          <div key={key} className="flex items-center gap-2">
            <div className={`relative border-2 rounded-lg px-4 py-3 min-w-[140px] text-center transition-all duration-300 ${statusColors[status]}`}>
              <div className="text-2xl mb-1">{config.icon}</div>
              <div className="text-xs font-semibold">{config.label}</div>
              {status === 'active' && (
                <div className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping"></div>
              )}
              {isFirewall && firewallFlags !== null && (
                <div className={`absolute -top-2 -right-2 px-2 py-0.5 text-xs rounded-full ${firewallBadge.className}`}>
                  {firewallBadge.text}
                </div>
              )}
            </div>
            {idx < Object.keys(stageConfig).length - 1 && (
              <div className={`text-2xl ${status === 'complete' ? 'text-green-500' : 'text-gray-300'}`}>
                →
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

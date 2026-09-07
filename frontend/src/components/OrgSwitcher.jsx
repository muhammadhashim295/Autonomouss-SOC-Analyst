import { useAuth, PRESET_ACCOUNTS } from '../context/AuthContext'

export default function OrgSwitcher() {
  const { currentUser, organizations, selectedOrgId, setSelectedOrgId, setIsLoginModalOpen, logout } = useAuth()

  // Find active preset metadata if matched
  const activePreset = PRESET_ACCOUNTS.find((a) => a.email === currentUser?.email)

  return (
    <div className="flex items-center gap-3 bg-slate-900/90 border border-slate-800/80 px-3 py-1.5 rounded-xl shadow-inner font-mono text-xs">
      {/* Role / Org Status Indicator */}
      {currentUser ? (
        <div className="flex items-center gap-2">
          {currentUser.is_admin ? (
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 tracking-wider">
                ADMIN
              </span>
              <label className="text-slate-400 text-[11px] hidden sm:inline">Tenant Filter:</label>
              <select
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
                className="bg-slate-950 border border-slate-700 text-white rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-purple-500"
              >
                <option value="ALL">🌐 All Organizations (Global View)</option>
                {organizations.map((org) => (
                  <option key={org.id || org.code} value={org.id || org.code}>
                    {org.code} — {org.name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-300 font-semibold truncate max-w-[200px]">
                {currentUser.org_name || activePreset?.name || 'Client Org'}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 uppercase tracking-wide">
                {currentUser.sector || activePreset?.sector || 'SECURED TENANT'}
              </span>
            </div>
          )}

          {/* User Email Pill */}
          <div className="hidden md:flex items-center gap-1.5 pl-2 border-l border-slate-800 text-slate-400 text-[11px]">
            <span>{currentUser.email}</span>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-slate-400">
          <span className="w-2 h-2 rounded-full bg-amber-400" />
          <span className="text-[11px]">Unauthenticated (Public Sandbox)</span>
        </div>
      )}

      {/* Switcher / Sign-In Button */}
      <button
        onClick={() => setIsLoginModalOpen(true)}
        className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 transition flex items-center gap-1.5 cursor-pointer ml-auto text-[11px]"
      >
        <span>⚡ Switch Role</span>
      </button>

      {currentUser && (
        <button
          onClick={logout}
          title="Sign out of current tenant"
          className="text-slate-500 hover:text-red-400 p-1 rounded transition cursor-pointer"
        >
          ✕
        </button>
      )}
    </div>
  )
}

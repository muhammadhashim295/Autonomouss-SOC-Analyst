import TypewriterText from './TypewriterText'

/**
 * Live agent reasoning panel with structured when/where/why/how context
 * and MITRE ATT&CK tactics display.
 */
export default function AgentPanel({ name, status, reasoning, verdict, confidence, extra, alertTime }) {
  const isActive = status === 'thinking' || status === 'running'
  const isDone = status === 'complete'

  return (
    <div className={`rounded-lg border transition-all duration-500 ${
      isDone ? 'cyber-border-active bg-emerald-950/20' :
      isActive ? 'border-yellow-500/30 bg-yellow-950/10' :
      'border-slate-800/50 bg-slate-900/30'
    }`}>
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-slate-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            isDone ? 'bg-emerald-400' :
            isActive ? 'bg-yellow-400 animate-pulse-glow' :
            'bg-slate-600'
          }`} />
          <span className="font-mono text-sm text-white">{name}</span>
        </div>
        {isDone && verdict && (
          <span className={`px-2 py-0.5 rounded text-xs font-mono ${
            verdict === 'true_positive'
              ? 'bg-red-500/20 text-red-400 border border-red-500/30'
              : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
          }`}>
            {verdict === 'true_positive' ? 'TRUE POSITIVE' : 'FALSE POSITIVE'}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="p-4 min-h-[140px]">
        {/* Waiting */}
        {status === 'idle' && (
          <div className="flex items-center justify-center h-full min-h-[120px]">
            <span className="text-slate-600 font-mono text-sm">Awaiting investigation</span>
          </div>
        )}

        {/* Thinking indicator */}
        {isActive && !reasoning && (
          <div className="flex flex-col gap-3 animate-fade-in">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" style={{ animationDelay: '0.2s' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" style={{ animationDelay: '0.4s' }} />
              <span className="text-yellow-400/70 font-mono text-sm ml-1">Analyzing evidence</span>
            </div>
            <div className="h-1 bg-slate-800 rounded overflow-hidden">
              <div className="h-full bg-yellow-500/50 rounded" style={{
                width: '30%',
                animation: 'pulse-glow 1.5s ease-in-out infinite',
              }} />
            </div>
          </div>
        )}

        {/* Reasoning */}
        {reasoning && (
          <div className="animate-fade-in">
            {/* When/Where/Why/How context bar */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-3 pb-3 border-b border-slate-800/40">
              <ContextItem label="WHEN" value={alertTime ? new Date(alertTime).toLocaleTimeString() : '—'} color="cyan" />
              <ContextItem label="WHERE" value={extra?.source_ip || extra?.source || 'alert payload'} color="cyan" />
              <ContextItem
                label="WHY"
                value={verdict === 'true_positive' ? 'Threat indicators confirmed' :
                       verdict === 'false_positive' ? 'Insufficient threat evidence' :
                       'Analysis in progress'}
                color={verdict === 'true_positive' ? 'red' : verdict === 'false_positive' ? 'emerald' : 'yellow'}
              />
              <ContextItem
                label="HOW"
                value={extra?.attack_technique || 'Agent reasoning below'}
                color="emerald"
              />
            </div>

            {/* Full reasoning with typewriter */}
            <div className="text-sm text-slate-300 font-mono leading-relaxed whitespace-pre-wrap max-h-[350px] overflow-y-auto">
              <TypewriterText text={reasoning} speed={6} />
            </div>

            {/* MITRE ATT&CK Tactics Bar */}
            {isDone && extra?.attack_technique && (
              <div className="mt-3 pt-3 border-t border-slate-800/40">
                <div className="text-xs font-mono text-slate-500 mb-1.5">MITRE ATT&CK</div>
                <div className="flex flex-wrap gap-1.5">
                  {parseAttackTechniques(extra.attack_technique).map((tech, i) => (
                    <span key={i} className="px-2 py-0.5 rounded text-xs font-mono bg-red-500/15 text-red-400 border border-red-500/25">
                      {tech}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Verdict metrics */}
            {isDone && confidence != null && (
              <div className="mt-3 pt-3 border-t border-slate-800/40 flex flex-wrap gap-3">
                <span className="text-xs font-mono text-slate-500">
                  Confidence: <span className="text-cyan-400">{(confidence * 100).toFixed(0)}%</span>
                </span>
                {extra?.impact_level && (
                  <span className="text-xs font-mono text-slate-500">
                    Impact: <span className={
                      extra.impact_level === 'high_impact' ? 'text-red-400' : 'text-emerald-400'
                    }>{extra.impact_level.replace('_', ' ').toUpperCase()}</span>
                  </span>
                )}
                {extra?.secondary_verdict && (
                  <span className="text-xs font-mono text-slate-500">
                    2nd Verdict: <span className={
                      extra.secondary_verdict === 'agree' || extra.secondary_verdict === 'true_positive'
                        ? 'text-red-400' : 'text-emerald-400'
                    }>{extra.secondary_verdict.replace('_', ' ')}</span>
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Helpers ── */

function ContextItem({ label, value, color = 'slate' }) {
  const colors = {
    cyan: 'text-cyan-400',
    emerald: 'text-emerald-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    slate: 'text-slate-400',
  }
  return (
    <div className="flex gap-1.5 text-xs font-mono">
      <span className="text-slate-600 flex-shrink-0">{label}:</span>
      <span className={`${colors[color]} truncate`} title={value}>{value}</span>
    </div>
  )
}

/** Parse attack_technique into individual IDs (handles "T1110.001, T1078" etc.) */
function parseAttackTechniques(tech) {
  if (!tech) return []
  if (Array.isArray(tech)) return tech
  return tech.split(/[,;]\s*/).filter(Boolean)
}

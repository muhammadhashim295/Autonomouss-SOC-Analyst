import TypewriterText from './TypewriterText'

/**
 * Live Agent Reasoning Panel.
 * Renders live stream deltas, confidence score, MITRE ATT&CK badges,
 * and structured context (WHEN / WHERE / WHY / HOW).
 */
export default function AgentPanel({ name, status, reasoning, verdict, confidence, extra, alertTime }) {
  const isActive = status === 'thinking' || status === 'running'
  const isDone = status === 'complete'

  return (
    <div className={`glass-panel rounded-2xl overflow-hidden transition-all duration-500 border ${
      isDone
        ? 'border-emerald-500/40 glow-green'
        : isActive
        ? 'border-amber-500/40 glow-amber'
        : 'border-slate-800/80'
    }`}>
      {/* Panel Header */}
      <div className="px-5 py-3.5 border-b border-slate-800/80 bg-slate-950/60 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={`w-2.5 h-2.5 rounded-full ${
            isDone ? 'bg-emerald-400' :
            isActive ? 'bg-amber-400 animate-pulse' :
            'bg-slate-600'
          }`} />
          <span className="font-display font-bold text-sm text-white">{name}</span>
        </div>

        {isDone && verdict && (
          <span className={`px-2.5 py-0.5 rounded-lg text-xs font-mono font-bold border uppercase tracking-wider ${
            verdict === 'true_positive'
              ? 'bg-red-500/20 text-red-400 border-red-500/40 glow-red'
              : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 glow-green'
          }`}>
            {verdict === 'true_positive' ? 'TRUE POSITIVE' : 'FALSE POSITIVE'}
          </span>
        )}
      </div>

      {/* Body Area */}
      <div className="p-5 min-h-[220px] flex flex-col justify-between">
        
        {/* Waiting State */}
        {status === 'idle' && !reasoning && !isDone && (
          <div className="flex-1 flex flex-col items-center justify-center py-10 text-center">
            <span className="text-slate-600 font-mono text-xs mb-1">Agent Standby</span>
            <span className="text-slate-500 text-xs font-mono">Awaiting investigation dispatch...</span>
          </div>
        )}

        {/* Thinking Pulse State */}
        {isActive && !reasoning && (
          <div className="flex-1 flex flex-col items-center justify-center py-8 space-y-3 animate-fade-in">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style={{ animationDelay: '0.2s' }} />
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" style={{ animationDelay: '0.4s' }} />
              <span className="text-amber-300 font-mono text-xs font-semibold ml-1">Analyzing log evidence & RAG context</span>
            </div>
            <div className="w-full max-w-xs h-1 bg-slate-800 rounded-full overflow-hidden">
              <div className="h-full bg-amber-400 rounded-full animate-pulse-glow" style={{ width: '65%' }} />
            </div>
          </div>
        )}

        {/* Reasoning Text & Context (Renders whenever reasoning or completion data is available) */}
        {(reasoning || isDone) && (
          <div className="animate-fade-in space-y-4">
            
            {/* Structured Context Grid */}
            <div className="grid grid-cols-2 gap-3 p-3 rounded-xl border border-slate-800/80 bg-slate-950/60">
              <ContextItem label="WHEN" value={alertTime ? new Date(alertTime).toLocaleTimeString() : '—'} color="cyan" />
              <ContextItem label="WHERE" value={extra?.source_ip || extra?.source || 'alert payload'} color="cyan" />
              <ContextItem
                label="WHY"
                value={verdict === 'true_positive' ? 'Confirmed threat indicators' :
                       verdict === 'false_positive' ? 'Insufficient threat markers' :
                       'Investigation ongoing'}
                color={verdict === 'true_positive' ? 'red' : verdict === 'false_positive' ? 'emerald' : 'amber'}
              />
              <ContextItem
                label="HOW"
                value={extra?.attack_technique || 'Deep agent reasoning'}
                color="emerald"
              />
            </div>

            {/* Reasoning Box with Typewriter Effect */}
            <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/80 text-xs text-slate-200 font-mono leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
              <TypewriterText text={reasoning || 'Agent reasoning processing complete.'} speed={6} />
            </div>

            {/* MITRE ATT&CK Badges */}
            {isDone && extra?.attack_technique && (
              <div className="pt-2 border-t border-slate-800/60">
                <div className="text-[11px] font-mono text-slate-500 mb-1.5 uppercase tracking-wider">MITRE ATT&CK Mapping</div>
                <div className="flex flex-wrap gap-1.5">
                  {parseAttackTechniques(extra.attack_technique).map((tech, i) => (
                    <span key={i} className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-red-500/15 text-red-300 border border-red-500/30">
                      {tech}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Metrics Footer Bar */}
            {isDone && confidence != null && (
              <div className="pt-2 border-t border-slate-800/60 flex flex-wrap items-center justify-between text-xs font-mono text-slate-400">
                <div>
                  Confidence: <span className="text-cyan-400 font-semibold font-mono">{(confidence * 100).toFixed(0)}%</span>
                </div>
                {extra?.impact_level && (
                  <div>
                    Impact: <span className={
                      extra.impact_level === 'high_impact' ? 'text-red-400 font-bold' : 'text-emerald-400 font-bold'
                    }>{extra.impact_level.replace('_', ' ').toUpperCase()}</span>
                  </div>
                )}
                {extra?.secondary_verdict && (
                  <div>
                    Secondary: <span className={
                      extra.secondary_verdict === 'agree' || extra.secondary_verdict === 'true_positive'
                        ? 'text-red-400 font-semibold' : 'text-emerald-400 font-semibold'
                    }>{extra.secondary_verdict.replace('_', ' ')}</span>
                  </div>
                )}
              </div>
            )}

          </div>
        )}


      </div>
    </div>
  )
}

function ContextItem({ label, value, color = 'slate' }) {
  const colors = {
    cyan: 'text-cyan-400 font-semibold',
    emerald: 'text-emerald-400 font-semibold',
    red: 'text-red-400 font-semibold',
    amber: 'text-amber-400 font-semibold',
    slate: 'text-slate-400',
  }
  return (
    <div className="flex items-center gap-1.5 text-xs font-mono overflow-hidden">
      <span className="text-slate-500 flex-shrink-0 text-[10px] uppercase">{label}:</span>
      <span className={`${colors[color]} truncate`} title={value}>{value}</span>
    </div>
  )
}

function parseAttackTechniques(tech) {
  if (!tech) return []
  if (Array.isArray(tech)) return tech
  return tech.split(/[,;]\s*/).filter(Boolean)
}

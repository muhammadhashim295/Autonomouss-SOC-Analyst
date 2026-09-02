import TypewriterText from './TypewriterText'

/**
 * Live agent reasoning panel.
 * Shows thinking indicator during agent_status events,
 * then reveals full reasoning with typewriter animation on agent_delta.
 */
export default function AgentPanel({ name, status, reasoning, verdict, confidence, extra }) {
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
              <span className="text-yellow-400/70 font-mono text-sm ml-1">Analyzing</span>
            </div>
            <div className="h-1 bg-slate-800 rounded overflow-hidden">
              <div className="h-full bg-yellow-500/50 rounded" style={{
                width: '30%',
                animation: 'pulse-glow 1.5s ease-in-out infinite',
              }} />
            </div>
          </div>
        )}

        {/* Reasoning with typewriter */}
        {reasoning && (
          <div className="animate-fade-in">
            <div className="text-sm text-slate-300 font-mono leading-relaxed whitespace-pre-wrap">
              <TypewriterText text={reasoning} speed={6} />
            </div>
            {/* Verdict info */}
            {isDone && confidence != null && (
              <div className="mt-3 pt-3 border-t border-slate-800/50 flex flex-wrap gap-2">
                <span className="text-xs font-mono text-slate-500">
                  Confidence: <span className="text-cyan-400">{(confidence * 100).toFixed(0)}%</span>
                </span>
                {extra?.attack_technique && (
                  <span className="text-xs font-mono text-slate-500">
                    MITRE: <span className="text-emerald-400">{extra.attack_technique}</span>
                  </span>
                )}
                {extra?.secondary_verdict && (
                  <span className="text-xs font-mono text-slate-500">
                    2nd Verdict: <span className={
                      extra.secondary_verdict === 'agree' || extra.secondary_verdict === 'true_positive'
                        ? 'text-red-400' : 'text-emerald-400'
                    }>{extra.secondary_verdict}</span>
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

import { useState } from 'react'

/**
 * Interactive Escalation Modal for cases in awaiting_approval or escalated status.
 * Allows analysts to approve the suggested action, redirect to a custom action,
 * or self-act (manual handling). Triggers backend decision submission and RAG memory write.
 */
export default function EscalationModal({ caseData, alertData, onClose, onSubmitDecision }) {
  const [decisionType, setDecisionType] = useState('approved') // 'approved' | 'redirected' | 'self_acted'
  const [analystAction, setAnalystAction] = useState('')
  const [analystReasoning, setAnalystReasoning] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)

  if (!caseData) return null

  const actionTaken = caseData.action_taken_parsed || {}
  const suggestedAction = actionTaken.action || 'open_ticket'
  const target = actionTaken.target || alertData?.alert_type || 'system'
  const impactLevel = caseData.impact_level || 'standard'
  const isHighImpact = impactLevel === 'high_impact'

  const handleSubmit = async (e) => {
    e.preventDefault()
    if ((decisionType === 'redirected' || decisionType === 'self_acted') && !analystAction.trim()) {
      setError('Please specify the action taken.')
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      await onSubmitDecision({
        decision: decisionType,
        analyst_action: decisionType === 'approved' ? suggestedAction : analystAction.trim(),
        analyst_reasoning: analystReasoning.trim() || undefined,
      })
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to record decision')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-2xl overflow-hidden glass-panel border border-emerald-500/30 rounded-2xl shadow-2xl glow-cyan animate-slide-up">
        
        {/* Top Glowing Header */}
        <div className={`px-6 py-4 border-b flex items-center justify-between ${
          isHighImpact
            ? 'bg-red-950/40 border-red-500/30'
            : 'bg-amber-950/30 border-amber-500/30'
        }`}>
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${
              isHighImpact ? 'bg-red-500 animate-ping' : 'bg-amber-400 animate-pulse'
            }`} />
            <div>
              <h2 className="font-display font-bold text-lg text-white flex items-center gap-2">
                Analyst Escalation & Decision Required
                <span className={`px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase ${
                  isHighImpact
                    ? 'bg-red-500/20 text-red-400 border border-red-500/40 glow-red'
                    : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                }`}>
                  {isHighImpact ? '⚠ HIGH IMPACT' : 'PAUSED IN APPROVAL MODE'}
                </span>
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                Case ID: {caseData.id?.slice(0, 18)}...
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xl font-mono px-2 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          
          {/* Summary Box */}
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 grid grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-slate-500 font-mono mb-1">Target Asset / IOC</div>
              <div className="text-sm font-mono text-cyan-400 font-semibold truncate">{target}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 font-mono mb-1">Suggested Agent Action</div>
              <div className="text-sm font-mono text-emerald-400 font-semibold truncate">
                {suggestedAction.replace('_', ' ').toUpperCase()}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500 font-mono mb-1">Primary Agent Verdict</div>
              <div className="text-xs font-mono text-slate-300">
                {caseData.primary_verdict?.toUpperCase() || 'TP'} ({((caseData.primary_confidence || 0.85) * 100).toFixed(0)}% conf)
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500 font-mono mb-1">Secondary Cross-Check</div>
              <div className="text-xs font-mono text-slate-300">
                {caseData.secondary_verdict?.toUpperCase() || 'AGREE'}
              </div>
            </div>
          </div>

          {/* Rationale explanation */}
          {actionTaken.reason && (
            <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/40 text-xs font-mono text-slate-300">
              <span className="text-amber-400 font-semibold">Gating Rationale: </span>
              {actionTaken.reason}
            </div>
          )}

          {/* Decision Selection Tabs */}
          <div>
            <label className="block text-xs font-mono text-slate-400 uppercase tracking-wider mb-2">
              Select Analyst Action
            </label>
            <div className="grid grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => setDecisionType('approved')}
                className={`p-3 rounded-xl border font-mono text-xs text-left transition-all duration-200 ${
                  decisionType === 'approved'
                    ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300 glow-green font-semibold'
                    : 'border-slate-800 bg-slate-900/40 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span>✓ APPROVE</span>
                  {decisionType === 'approved' && <span className="text-emerald-400">●</span>}
                </div>
                <div className="text-[11px] text-slate-500 leading-tight">Execute agent's suggested action</div>
              </button>

              <button
                type="button"
                onClick={() => setDecisionType('redirected')}
                className={`p-3 rounded-xl border font-mono text-xs text-left transition-all duration-200 ${
                  decisionType === 'redirected'
                    ? 'border-cyan-500 bg-cyan-500/15 text-cyan-300 glow-cyan font-semibold'
                    : 'border-slate-800 bg-slate-900/40 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span>↺ REDIRECT</span>
                  {decisionType === 'redirected' && <span className="text-cyan-400">●</span>}
                </div>
                <div className="text-[11px] text-slate-500 leading-tight">Specify alternative response action</div>
              </button>

              <button
                type="button"
                onClick={() => setDecisionType('self_acted')}
                className={`p-3 rounded-xl border font-mono text-xs text-left transition-all duration-200 ${
                  decisionType === 'self_acted'
                    ? 'border-purple-500 bg-purple-500/15 text-purple-300 glow-purple font-semibold'
                    : 'border-slate-800 bg-slate-900/40 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span>✋ SELF-ACT</span>
                  {decisionType === 'self_acted' && <span className="text-purple-400">●</span>}
                </div>
                <div className="text-[11px] text-slate-500 leading-tight">Handled manually outside platform</div>
              </button>
            </div>
          </div>

          {/* Conditional Inputs */}
          {decisionType !== 'approved' && (
            <div className="animate-fade-in space-y-3">
              <div>
                <label className="block text-xs font-mono text-slate-400 mb-1">
                  Specify Action Taken <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={analystAction}
                  onChange={(e) => setAnalystAction(e.target.value)}
                  placeholder={
                    decisionType === 'redirected'
                      ? 'e.g., isolate_host or block_ip 192.168.1.100'
                      : 'e.g., Reset AD user password manually and patched endpoint'
                  }
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                  required
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-mono text-slate-400 mb-1">
              Analyst Reasoning / Notes (stored in RAG memory for future learning)
            </label>
            <textarea
              value={analystReasoning}
              onChange={(e) => setAnalystReasoning(e.target.value)}
              placeholder="Explain why this decision was taken (e.g. Critical domain controller asset requires manual verification before host isolation)..."
              rows={3}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono focus:border-emerald-500 focus:outline-none"
            />
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-xs font-mono text-red-400">
              {error}
            </div>
          )}

          {/* Footer Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800/60">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg font-mono text-xs text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className={`px-6 py-2.5 rounded-xl font-mono text-xs font-semibold border transition-all duration-300 ${
                isSubmitting
                  ? 'border-slate-700 bg-slate-800 text-slate-500 cursor-wait'
                  : 'border-emerald-500/50 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 hover:border-emerald-400 glow-green cursor-pointer'
              }`}
            >
              {isSubmitting ? 'Submitting & Saving Memory...' : 'SUBMIT DECISION →'}
            </button>
          </div>

        </form>
      </div>
    </div>
  )
}

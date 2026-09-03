import { useEffect } from 'react'

/**
 * Animated Memory Toast Notification.
 * Appears when an analyst override or case completion writes a record
 * to the RAG memory store, visually proving the learning loop to judges.
 */
export default function MemoryToast({ toast, onClose }) {
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => {
      onClose()
    }, 6000)
    return () => clearTimeout(timer)
  }, [toast, onClose])

  if (!toast) return null

  const isCorrection = toast.recordType === 'correction'

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-slide-up max-w-md">
      <div className={`p-4 rounded-xl border glass-panel shadow-2xl flex items-start gap-3.5 ${
        isCorrection
          ? 'border-purple-500/50 bg-purple-950/60 glow-purple'
          : 'border-emerald-500/50 bg-emerald-950/60 glow-green'
      }`}>
        {/* Memory Icon */}
        <div className={`p-2.5 rounded-lg flex-shrink-0 ${
          isCorrection ? 'bg-purple-500/20 text-purple-300' : 'bg-emerald-500/20 text-emerald-300'
        }`}>
          <span className="text-xl">🧠</span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="font-display font-bold text-sm text-white flex items-center gap-1.5">
              RAG Memory Store Updated
              {isCorrection && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/30 text-purple-200 border border-purple-400/40">
                  +5 WEIGHT BOOST
                </span>
              )}
            </span>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 text-xs font-mono"
            >
              ✕
            </button>
          </div>

          <p className="text-xs text-slate-300 font-mono leading-relaxed line-clamp-2">
            {toast.message || (
              isCorrection
                ? 'Analyst correction indexed into Qoder Memory. Future similar alerts will prioritize this guidance.'
                : 'Case outcome indexed into Qoder Memory for similarity retrieval.'
            )}
          </p>

          <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Record: <span className="text-cyan-400">{toast.recordId ? toast.recordId.slice(0, 10) + '...' : 'Saved'}</span></span>
            <span className="text-slate-500">Live Learning</span>
          </div>
        </div>
      </div>
    </div>
  )
}

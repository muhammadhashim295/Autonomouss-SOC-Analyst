import React from 'react'

/**
 * Pitch & Demo Storyline Status Banner.
 * Renders live step progress, active threat story summary, timer, and controls
 * for hackathon presentations.
 */
export default function PitchDemoBanner({
  currentStep,
  totalSteps = 3,
  stepTitle,
  stepDescription,
  onCancel,
  onNext,
  isAutoAdvancing,
}) {
  const steps = [
    { num: 1, label: '1. False Positive Auto-Close', color: 'cyan' },
    { num: 2, label: '2. Log Poisoning Neutralized', color: 'red' },
    { num: 3, label: '3. Exfiltration Escalation & HITL', color: 'purple' },
  ]

  return (
    <div className="relative overflow-hidden rounded-2xl border border-cyan-500/40 bg-slate-950/80 p-4 shadow-2xl backdrop-blur-xl glow-cyan animate-slide-up">
      
      {/* Background Cyber Grid Lines */}
      <div className="absolute inset-0 bg-cyber-grid opacity-20 pointer-events-none" />

      <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-4">
        
        {/* Left: Pitch Mode Indicator & Story Details */}
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 border border-cyan-400/40 shadow-inner">
            <span className="text-xl animate-pulse">🚀</span>
          </div>

          <div>
            <div className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-cyan-400">
              <span className="inline-block h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
              <span>LIVE PITCH DEMO MODE</span>
              <span className="rounded bg-cyan-950/80 px-2 py-0.5 text-[10px] text-cyan-300 border border-cyan-500/30">
                STEP {currentStep} OF {totalSteps}
              </span>
            </div>

            <h3 className="font-display font-bold text-base text-white mt-0.5">
              {stepTitle}
            </h3>

            <p className="font-mono text-xs text-slate-300 mt-0.5 max-w-xl leading-relaxed">
              {stepDescription}
            </p>
          </div>
        </div>

        {/* Center: Step Pipeline Badges */}
        <div className="flex items-center gap-2 font-mono text-xs">
          {steps.map((s) => {
            const isActive = s.num === currentStep
            const isCompleted = s.num < currentStep
            return (
              <div
                key={s.num}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${
                  isActive
                    ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200 glow-cyan scale-105'
                    : isCompleted
                    ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-300'
                    : 'border-slate-800 bg-slate-900/40 text-slate-500'
                }`}
              >
                <span>{isCompleted ? '✓' : s.num}</span>
                <span className="hidden lg:inline">{s.label}</span>
              </div>
            )
          })}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 font-mono text-xs">
          {onNext && currentStep < totalSteps && (
            <button
              onClick={onNext}
              className="px-3.5 py-1.5 rounded-xl font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 transition-all cursor-pointer"
            >
              NEXT STEP ➔
            </button>
          )}

          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded-xl font-bold bg-slate-800/80 text-slate-400 hover:text-white border border-slate-700/60 transition-all cursor-pointer"
          >
            EXIT DEMO
          </button>
        </div>

      </div>
    </div>
  )
}

import TypewriterText from './TypewriterText'

/**
 * Panel showing an agent's live status and reasoning.
 * Displays "thinking" indicator during agent_status events,
 * then reveals full reasoning with typewriter animation on agent_complete.
 * 
 * @param {string} agentName - "primary" or "secondary"
 * @param {string} status - Current status: "idle" | "thinking" | "complete"
 * @param {string|null} reasoning - Full reasoning text (null until agent_complete)
 * @param {object|null} verdict - Parsed verdict data (from agent_complete)
 */
export default function AgentPanel({ agentName, status, reasoning, verdict }) {
  const statusColors = {
    idle: 'bg-gray-100 border-gray-300',
    thinking: 'bg-yellow-50 border-yellow-400',
    complete: 'bg-green-50 border-green-400',
  }

  const statusLabels = {
    idle: 'Waiting',
    thinking: 'Thinking...',
    complete: 'Complete',
  }

  return (
    <div className={`border-2 rounded-lg p-4 ${statusColors[status]} transition-colors duration-300`}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-800 capitalize">{agentName} Agent</h3>
        <span className={`px-2 py-1 text-xs rounded ${
          status === 'thinking' ? 'bg-yellow-200 text-yellow-800 animate-pulse' :
          status === 'complete' ? 'bg-green-200 text-green-800' :
          'bg-gray-200 text-gray-600'
        }`}>
          {statusLabels[status]}
        </span>
      </div>

      {status === 'thinking' && (
        <div className="text-sm text-gray-600 italic">
          Analyzing evidence and deriving findings...
        </div>
      )}

      {status === 'complete' && verdict && (
        <div className="mb-2 text-sm">
          <div className="flex gap-4">
            <span>
              <strong>Verdict:</strong>{' '}
              <span className={verdict.verdict === 'true_positive' ? 'text-red-600' : 'text-green-600'}>
                {verdict.verdict?.replace('_', ' ')}
              </span>
            </span>
            {verdict.confidence && (
              <span>
                <strong>Confidence:</strong> {(verdict.confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      )}

      {status === 'complete' && reasoning && (
        <div className="mt-3">
          <div className="text-xs font-semibold text-gray-600 mb-1">Reasoning:</div>
          <TypewriterText text={reasoning} duration={2500} />
        </div>
      )}
    </div>
  )
}

import { useEffect, useRef, useCallback } from 'react'
import { getBaseUrl } from '../utils/api'

// If no real SSE data event (agent delta, stage, verdict, completion) arrives
// within this window, the run is considered stalled: the backend relays only
// `: heartbeat` comments while a producer thread is thinking *or hung*, so a
// silent Primary→Secondary handoff failure would otherwise leave the UI stuck
// on "Investigation ongoing" forever. 120s is well beyond any legitimate gap
// (OTX enrichment caps at 15s, a full Groq report streams deltas continuously).
const INACTIVITY_TIMEOUT_MS = 120000

/**
 * Consume SSE from POST /alerts/{id}/investigate/stream.
 * Backend uses POST + StreamingResponse (not GET EventSource) to prevent
 * browser auto-reconnect from re-triggering investigations.
 *
 * Guarantees the consumer always sees a terminal event: a real
 * `investigation_complete`/`investigation_error` from the backend, or a
 * synthetic `investigation_error` when the stream closes early or goes silent.
 *
 * @param {string|null} alertId - Alert ID to investigate (null to disable)
 * @param {function} onEvent - Callback receiving { event: string, data: object }
 */
export function useSSE(alertId, onEvent) {
  const abortRef = useRef(null)
  const onEventRef = useRef(onEvent)

  useEffect(() => { onEventRef.current = onEvent }, [onEvent])

  useEffect(() => {
    if (!alertId) return

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    let sawTerminal = false
    let inactivityTimer = null

    const clearTimer = () => { if (inactivityTimer) { clearTimeout(inactivityTimer); inactivityTimer = null } }

    // Forward an event to the reducer, tracking terminal state and restarting
    // the inactivity watchdog on every genuine data event.
    const emit = (evt) => {
      if (evt.event === 'investigation_complete' || evt.event === 'investigation_error') {
        sawTerminal = true
        clearTimer()
      } else {
        armTimer()
      }
      onEventRef.current?.(evt)
    }

    const failTerminal = (detail) => {
      if (sawTerminal) return
      sawTerminal = true
      clearTimer()
      onEventRef.current?.({ event: 'investigation_error', data: { detail } })
    }

    function armTimer() {
      clearTimer()
      inactivityTimer = setTimeout(() => {
        failTerminal(
          `Stream stalled — no activity for ${INACTIVITY_TIMEOUT_MS / 1000}s. ` +
          'The investigation (likely the Secondary handoff) did not finish. Please retry.',
        )
        controller.abort()
      }, INACTIVITY_TIMEOUT_MS)
    }

    const stream = async () => {
      try {
        const token = localStorage.getItem('soc_access_token')
        const headers = {}
        if (token) {
          headers['Authorization'] = `Bearer ${token}`
        }

        const baseUrl = getBaseUrl()
        const res = await fetch(`${baseUrl}/alerts/${alertId}/investigate/stream`, {
          method: 'POST',
          headers,
          signal: controller.signal,
        })
        if (!res.ok) {
          failTerminal(`HTTP ${res.status}`)
          return
        }

        // Start the watchdog once the connection is open.
        armTimer()

        const reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''
        let eventName = null

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() // keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventName = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (eventName) emit({ event: eventName, data })
              } catch { /* skip malformed */ }
              eventName = null
            }
            // ': heartbeat' comments are silently ignored (they do NOT reset
            // the watchdog — only real data events prove forward progress).
          }
        }

        // Stream ended without the backend ever sending a terminal event:
        // convert the silent hang into a visible, retryable error.
        failTerminal(
          'Stream closed before the investigation completed — the Secondary handoff ' +
          'did not finish. Please retry.',
        )
      } catch (err) {
        if (err.name !== 'AbortError') {
          failTerminal(err.message)
        }
      } finally {
        clearTimer()
      }
    }

    stream()
    return () => { controller.abort(); clearTimer() }
  }, [alertId])
}

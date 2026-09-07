import { useEffect, useRef, useCallback } from 'react'
import { getBaseUrl } from '../utils/api'

/**
 * Consume SSE from POST /alerts/{id}/investigate/stream.
 * Backend uses POST + StreamingResponse (not GET EventSource) to prevent
 * browser auto-reconnect from re-triggering investigations.
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
          onEventRef.current?.({ event: 'investigation_error', data: { detail: `HTTP ${res.status}` } })
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
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
                if (eventName) onEventRef.current?.({ event: eventName, data })
              } catch { /* skip malformed */ }
              eventName = null
            }
            // ': heartbeat' comments are silently ignored
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          onEventRef.current?.({ event: 'investigation_error', data: { detail: err.message } })
        }
      }
    }

    stream()
    return () => controller.abort()
  }, [alertId])
}

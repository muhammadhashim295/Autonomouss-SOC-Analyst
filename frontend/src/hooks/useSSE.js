import { useEffect, useRef, useCallback } from 'react'

/**
 * Custom hook to consume SSE from the backend's POST /alerts/{id}/investigate/stream
 * endpoint. Parses event: + data: lines and calls onEvent for each parsed event.
 * 
 * @param {string|null} alertId - Alert ID to stream (null to disable)
 * @param {function} onEvent - Callback receiving { event: string, data: object }
 * @param {function} [onError] - Optional error callback
 */
export function useSSE(alertId, onEvent, onError) {
  const abortControllerRef = useRef(null)

  useEffect(() => {
    if (!alertId) return

    // Cancel previous stream if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const controller = new AbortController()
    abortControllerRef.current = controller

    const streamInvestigation = async () => {
      try {
        const response = await fetch(`/alerts/${alertId}/investigate/stream`, {
          method: 'POST',
          headers: { 'Accept': 'text/event-stream' },
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`Stream failed: ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = null

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.substring(6).trim()
            } else if (line.startsWith('data:')) {
              const dataStr = line.substring(5).trim()
              try {
                const data = JSON.parse(dataStr)
                if (onEvent && currentEvent) {
                  onEvent({ event: currentEvent, data })
                }
              } catch (err) {
                // Skip malformed JSON
              }
              currentEvent = null
            }
            // Skip empty lines and heartbeat comments (lines starting with ':')
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          // Intentional cancellation, ignore
          return
        }
        console.error('SSE stream error:', err)
        if (onError) onError(err)
      }
    }

    streamInvestigation()

    // Cleanup on unmount or alertId change
    return () => {
      controller.abort()
    }
  }, [alertId, onEvent, onError])

  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }, [])

  return { cancel }
}

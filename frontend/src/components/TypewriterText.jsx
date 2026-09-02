import { useState, useEffect } from 'react'

/**
 * Animated text reveal — types out text character-by-character.
 * Softens the "dump" when agent reasoning arrives as one message.
 */
export default function TypewriterText({ text, speed = 8 }) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!text) { setDisplayed(''); setDone(false); return }

    setDisplayed('')
    setDone(false)
    let i = 0
    const charsPerTick = Math.max(1, Math.ceil(text.length / (2500 / speed)))

    const timer = setInterval(() => {
      i += charsPerTick
      if (i >= text.length) {
        setDisplayed(text)
        setDone(true)
        clearInterval(timer)
      } else {
        setDisplayed(text.slice(0, i))
      }
    }, speed)

    return () => clearInterval(timer)
  }, [text, speed])

  if (!text) return null

  return (
    <span>
      {displayed}
      {!done && <span className="animate-blink text-emerald-400">▊</span>}
    </span>
  )
}

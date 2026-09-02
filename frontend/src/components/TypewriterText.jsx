import { useState, useEffect, useRef } from 'react'

/**
 * Animates text reveal character-by-character for a typewriter effect.
 * Used to soften the "dump" when agent reasoning arrives in one chunk.
 * 
 * @param {string} text - Full text to reveal
 * @param {number} [duration=2000] - Total animation duration in ms
 * @param {boolean} [animate=true] - Whether to animate (false = instant)
 */
export default function TypewriterText({ text, duration = 2000, animate = true }) {
  const [displayedText, setDisplayedText] = useState('')
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!text) {
      setDisplayedText('')
      return
    }

    if (!animate) {
      setDisplayedText(text)
      return
    }

    setDisplayedText('')
    const charsPerTick = Math.max(1, Math.floor(text.length / (duration / 30)))
    let currentIndex = 0

    intervalRef.current = setInterval(() => {
      currentIndex += charsPerTick
      if (currentIndex >= text.length) {
        setDisplayedText(text)
        clearInterval(intervalRef.current)
      } else {
        setDisplayedText(text.substring(0, currentIndex))
      }
    }, 30)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [text, duration, animate])

  return (
    <div className="whitespace-pre-wrap font-mono text-sm text-gray-700">
      {displayedText}
    </div>
  )
}

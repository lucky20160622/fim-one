import { useState, useCallback, useEffect } from "react"

const STORAGE_KEY = "workflow_favorites"

export function useWorkflowFavorites() {
  const [favorites, setFavorites] = useState<Set<string>>(new Set())

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) setFavorites(new Set(JSON.parse(stored)))
    } catch {
      /* corrupted data — ignore */
    }
  }, [])

  const toggleFavorite = useCallback((id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
      } catch {
        /* quota exceeded — ignore */
      }
      return next
    })
  }, [])

  const isFavorite = useCallback((id: string) => favorites.has(id), [favorites])

  return { favorites, toggleFavorite, isFavorite }
}

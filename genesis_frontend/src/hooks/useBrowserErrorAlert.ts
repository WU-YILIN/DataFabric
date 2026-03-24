import { useEffect, useRef } from 'react'

export const useBrowserErrorAlert = (error: string | null | undefined) => {
  const lastErrorRef = useRef<string | null>(null)

  useEffect(() => {
    if (!error) {
      lastErrorRef.current = null
      return
    }
    if (lastErrorRef.current === error) {
      return
    }
    lastErrorRef.current = error
    window.alert(error)
  }, [error])
}

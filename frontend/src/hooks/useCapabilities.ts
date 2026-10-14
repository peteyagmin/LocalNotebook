import { useCallback, useEffect, useState } from 'react'
import { api, type Capabilities } from '../api'

/** What this machine and these settings can do (OCR, speech model, network switches). */
export function useCapabilities() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const refresh = useCallback(() => {
    api
      .getCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null))
  }, [])
  useEffect(refresh, [refresh])
  return { capabilities, refresh }
}

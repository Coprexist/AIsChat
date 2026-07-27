import { useState, useEffect } from 'react'
import { api } from '../api/client'

const POLL_MS = 30_000

export function usePendingFriendRequests(): number {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let mounted = true

    const fetchCount = () => {
      api.get<unknown[]>('/friends/requests?status=pending&received_only=true').then((data) => {
        if (mounted) setCount(Array.isArray(data) ? data.length : 0)
      }).catch(() => {})
    }

    fetchCount()
    const iv = setInterval(fetchCount, POLL_MS)
    return () => { mounted = false; clearInterval(iv) }
  }, [])

  return count
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** 754 -> "12:34", 3725 -> "1:02:05" */
export function formatTimestamp(seconds: number): string {
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h ? String(m).padStart(2, '0') : String(m)
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`
}

interface Location {
  page?: number | null
  heading_path?: string[] | null
  start_seconds?: number
}

/** Where in a source a passage is: a timestamp, a page, or a heading path. */
export function describeLocation(location: Location): string {
  if (location.start_seconds !== undefined) return formatTimestamp(location.start_seconds)
  if (location.page) return `page ${location.page}`
  return location.heading_path?.join(' › ') ?? ''
}

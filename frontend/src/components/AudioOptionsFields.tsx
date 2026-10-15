import type { AudioFormat, AudioLength, AudioOptions } from '../api'

const LENGTHS: { value: AudioLength; label: string }[] = [
  { value: 'short', label: 'Short (~5 min)' },
  { value: 'default', label: 'Default (~10 min)' },
  { value: 'long', label: 'Long (~20 min)' },
]
const FORMATS: { value: AudioFormat; label: string }[] = [
  { value: 'deep_dive', label: 'Deep dive' },
  { value: 'brief', label: 'Brief' },
  { value: 'debate', label: 'Debate' },
  { value: 'critique', label: 'Critique' },
]

const selectClass =
  'mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900'

/** Length and format of an audio overview (FR-6.2). */
export function AudioOptionsFields({
  value,
  onChange,
}: {
  value: AudioOptions
  onChange: (options: AudioOptions) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="text-xs">
        Length
        <select
          aria-label="Length"
          value={value.length}
          onChange={(e) => onChange({ ...value, length: e.target.value as AudioLength })}
          className={selectClass}
        >
          {LENGTHS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs">
        Format
        <select
          aria-label="Format"
          value={value.format}
          onChange={(e) => onChange({ ...value, format: e.target.value as AudioFormat })}
          className={selectClass}
        >
          {FORMATS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

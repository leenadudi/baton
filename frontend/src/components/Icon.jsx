// Inline stroke icons for the nav rail and top bar. Kept local so the app takes
// no icon dependency, and aria-hidden because every one sits next to a text label.
const P = {
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  list: 'M4 6h16M4 12h16M4 18h10',
  brief: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h7M10 17h5',
  patient: 'M12 11a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0',
  reset: 'M4 12a8 8 0 1114 5M4 12V6M4 12h6',
  search: 'M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3',
  back: 'M15 5l-7 7 7 7',
  notes: 'M6 3h12v18H6zM9 8h6M9 12h6M9 16h4',
}

export default function Icon({ name, className = 'ico' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[name]} />
    </svg>
  )
}

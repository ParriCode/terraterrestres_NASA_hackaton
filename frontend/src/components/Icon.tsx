import type { SVGProps, ReactNode } from 'react'

type IconName = 'menu' | 'x' | 'plus' | 'minus' | 'crosshair' | 'eye' | 'eye-off' | 'trash' | 'play' | 'pause' | 'rotate' | 'chevron-left' | 'arrow-right' | 'rocket' | 'clock' | 'calendar' | 'download' | 'info' | 'globe' | 'layers' | 'settings' | 'check' | 'alert' | 'orbit' | 'target'
type Props = SVGProps<SVGSVGElement> & { name: IconName; size?: number }

export default function Icon({ name, size = 18, ...props }: Props) {
  const attrs = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  const items: Record<IconName, ReactNode> = {
    menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
    x: <path d="M5 5l14 14M19 5L5 19" />,
    plus: <path d="M12 4v16M4 12h16" />,
    minus: <path d="M4 12h16" />,
    crosshair: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2" /><path d="M12 1v4M12 19v4M1 12h4M19 12h4" /></>,
    eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    'eye-off': <><path d="M2 2l20 20M4.5 7.2C2.8 9 2 12 2 12s4 7 10 7c2.1 0 4-.7 5.6-1.7M9.4 5.4A12 12 0 0 1 12 5c6 0 10 7 10 7s-.8 1.5-2 3" /></>,
    trash: <><path d="M4 7h16M10 3h4M6 7l1 14h10l1-14M10 11v7M14 11v7" /></>,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    pause: <><path d="M8 5v14M16 5v14" /></>,
    rotate: <><path d="M3 11a9 9 0 1 1 3 7M3 4v7h7" /></>,
    'chevron-left': <path d="m15 5-7 7 7 7" />,
    'arrow-right': <><path d="M3 12h17m-7-7 7 7-7 7" /></>,
    rocket: <><path d="M5 13c-1 1-2 4-2 6l5-2M11 19l-2 2c-1-2-1-4 0-6l6-6c4-4 6-4 7-4 0 2 0 5-4 9l-6 5Z" /><circle cx="16" cy="10" r="1.5" /><path d="m8 16-3-3" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l4 2" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c-5 5-5 13 0 18 5-5 5-13 0-18" /></>,
    layers: <><path d="m12 2 10 6-10 6L2 8l10-6ZM2 13l10 6 10-6M2 18l10 4 10-4" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M9 2h6l1 3 3 1 2-1 2 5-2 2 0 2 2 2-2 5-3-1-2 1-1 2H9l-1-3-3-1-2 1-2-5 2-2v-2l-2-2 2-5 3 1 2-1Z" /></>,
    check: <path d="m4 12 5 5 11-11" />,
    alert: <><path d="m12 2 10 19H2L12 2ZM12 9v5M12 18h.01" /></>,
    orbit: <><circle cx="12" cy="12" r="3" /><ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(-34 12 12)" /></>,
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
  }
  return <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...attrs} {...props}>{items[name]}</svg>
}

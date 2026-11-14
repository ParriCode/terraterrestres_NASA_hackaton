/** Iconos de Font Awesome Free con la interfaz <Icon name="..." />. */
import type { CSSProperties } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faXmark, faPlus, faMinus, faCrosshairs, faPlay, faPause, faRotateLeft, faRocket, faClock,
  faEarthAmericas, faLayerGroup, faTriangleExclamation, faSatellite, faBullseye,
} from '@fortawesome/free-solid-svg-icons'

const ICONS = {
  x: faXmark, plus: faPlus, minus: faMinus, crosshair: faCrosshairs, play: faPlay, pause: faPause,
  rotate: faRotateLeft, rocket: faRocket, clock: faClock, globe: faEarthAmericas, layers: faLayerGroup,
  alert: faTriangleExclamation, orbit: faSatellite, target: faBullseye,
} satisfies Record<string, IconDefinition>

type Props = { name: keyof typeof ICONS; size?: number; className?: string; style?: CSSProperties }

export default function Icon({ name, size = 18, className, style }: Props) {
  return <FontAwesomeIcon icon={ICONS[name]} className={className} aria-hidden="true"
    style={{ width: size, height: size, flexShrink: 0, ...style }} />
}

/**
 * Iconos oficiales de Font Awesome Free. No hay trazos SVG inventados.
 * Se conserva la interfaz <Icon name="..." /> para no tener que editar
 * todos los componentes que ya consumen este archivo.
 */
import type { CSSProperties } from 'react'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import type { IconDefinition } from '@fortawesome/fontawesome-svg-core'
import {
  faBars, faXmark, faPlus, faMinus, faCrosshairs, faEye,
  faEyeSlash, faTrashCan, faPlay, faPause, faRotateLeft,
  faChevronLeft, faArrowRight, faRocket, faClock, faCalendarDays,
  faDownload, faCircleInfo, faEarthAmericas, faLayerGroup, faGear,
  faCheck, faTriangleExclamation, faSatellite, faBullseye,
} from '@fortawesome/free-solid-svg-icons'

type IconName = 'menu' | 'x' | 'plus' | 'minus' | 'crosshair' | 'eye' | 'eye-off' | 'trash' | 'play' | 'pause' | 'rotate' | 'chevron-left' | 'arrow-right' | 'rocket' | 'clock' | 'calendar' | 'download' | 'info' | 'globe' | 'layers' | 'settings' | 'check' | 'alert' | 'orbit' | 'target'
type Props = { name: IconName; size?: number; className?: string; style?: CSSProperties }

const ICONS: Record<IconName, IconDefinition> = {
  menu: faBars,
  x: faXmark,
  plus: faPlus,
  minus: faMinus,
  crosshair: faCrosshairs,
  eye: faEye,
  'eye-off': faEyeSlash,
  trash: faTrashCan,
  play: faPlay,
  pause: faPause,
  rotate: faRotateLeft,
  'chevron-left': faChevronLeft,
  'arrow-right': faArrowRight,
  rocket: faRocket,
  clock: faClock,
  calendar: faCalendarDays,
  download: faDownload,
  info: faCircleInfo,
  globe: faEarthAmericas,
  layers: faLayerGroup,
  settings: faGear,
  check: faCheck,
  alert: faTriangleExclamation,
  orbit: faSatellite,
  target: faBullseye,
}

export default function Icon({ name, size = 18, className, style }: Props) {
  return <FontAwesomeIcon icon={ICONS[name]} className={className} aria-hidden="true"
    style={{ width: size, height: size, flexShrink: 0, ...style }} />
}

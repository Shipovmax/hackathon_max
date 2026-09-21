// Свой набор иконок: в @maxhub/max-ui 0.5.0 их всего шесть (шеврон, крестик, поиск).
// Рисуем контуром в currentColor, поэтому иконка живёт в любой теме и на кнопке
// любого цвета.
type IconName =
  | 'back'
  | 'forward'
  | 'close'
  | 'refresh'
  | 'plus'
  | 'camera'
  | 'calendar'
  | 'store'
  | 'people'
  | 'clock'
  | 'alert'
  | 'copy'
  | 'sun'
  | 'moon';

const PATHS: Record<IconName, string> = {
  back: 'M15 5l-7 7 7 7',
  forward: 'M9 5l7 7-7 7',
  close: 'M6 6l12 12M18 6L6 18',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4',
  plus: 'M12 5v14M5 12h14',
  camera: 'M3 8.5A1.5 1.5 0 0 1 4.5 7h2L8 5h8l1.5 2h2A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5zM12 16a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
  calendar: 'M4 8h16M7 4v3m10-3v3M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z',
  store: 'M4 10v9a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-9M3 10l1.6-5.2A1 1 0 0 1 5.6 4h12.8a1 1 0 0 1 1 .8L21 10a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z',
  people: 'M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 19v-1.5a3.5 3.5 0 0 0-2.6-3.4M15.5 4.6a3.5 3.5 0 0 1 0 6.8',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7.5V12l3 2',
  alert: 'M12 9v4.5M12 17h.01M10.3 4.3 2.8 17.2a1.6 1.6 0 0 0 1.4 2.4h15.6a1.6 1.6 0 0 0 1.4-2.4L13.7 4.3a1.6 1.6 0 0 0-2.8 0z',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 2v2m0 16v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M2 12h2m16 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z',
  copy: 'M9 9V5.5A1.5 1.5 0 0 1 10.5 4h8A1.5 1.5 0 0 1 20 5.5v8a1.5 1.5 0 0 1-1.5 1.5H15M5.5 9h8A1.5 1.5 0 0 1 15 10.5v8a1.5 1.5 0 0 1-1.5 1.5h-8A1.5 1.5 0 0 1 4 18.5v-8A1.5 1.5 0 0 1 5.5 9z',
};

interface IconProps {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 20 }: IconProps) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

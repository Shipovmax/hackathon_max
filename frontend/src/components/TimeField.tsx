import { Typography } from '@maxhub/max-ui';
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';

import { isValidTime } from '../lib/format';

/** Высота строки колеса, px. Держим в паре с --wheel-item в styles.css. */
const ITEM = 40;
const HOURS = Array.from({ length: 24 }, (_, index) => index);
const MINUTES = Array.from({ length: 60 }, (_, index) => index);
const OPENED = 'timefield:open';

const pad = (value: number) => String(value).padStart(2, '0');

interface WheelProps {
  label: string;
  values: number[];
  value: number;
  onChange: (value: number) => void;
}

/** Одно колесо: прокрутка «щёлкает» по строкам, выбранная строка стоит по центру. */
function Wheel({ label, values, value, onChange }: WheelProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const held = useRef(false);
  // Строка, на которой стоит колесо. С внешним значением она расходится, только когда его
  // изменили снаружи (открылась панель, нажали стрелку): тогда колесо переставляем. Пока
  // человек крутит сам, новое значение уходит наружу и здесь совпадает с ним.
  const shown = useRef<number | null>(null);
  // Строка, к которой колесо едет после тапа. Пока едет, промежуточные строки не выбираем:
  // иначе тап по «08» от «22» мог остановиться на «18», если прокрутка запнулась.
  const picking = useRef<number | null>(null);

  const moveTo = (target: number) => {
    const element = scroller.current;
    if (!element) return;
    const top = Math.max(0, values.indexOf(target)) * ITEM;
    if (Math.abs(element.scrollTop - top) > 1) element.scrollTop = top;
  };

  useEffect(() => {
    if (shown.current === value) return;
    shown.current = value;
    moveTo(value);
  });

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const onScroll = () => {
    const element = scroller.current;
    if (!element) return;
    if (picking.current === null) {
      const next = values[Math.min(values.length - 1, Math.max(0, Math.round(element.scrollTop / ITEM)))];
      if (next !== shown.current) {
        shown.current = next;
        onChange(next);
      }
    }
    // Когда событий нет 140 мс, прокрутка закончилась. Если браузер не умеет
    // прилипание к строкам, колесо доводим до выбранной строки сами.
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (picking.current !== null) {
        // Поездка к нажатой строке закончилась или прервалась — ставим колесо ровно на неё.
        const target = picking.current;
        picking.current = null;
        moveTo(target);
        return;
      }
      if (!held.current && shown.current !== null) moveTo(shown.current);
    }, 140);
  };

  /** Тап по строке выбирает её сразу, а прокрутка лишь показывает выбор. */
  const pick = (target: number) => {
    shown.current = target;
    onChange(target);
    const element = scroller.current;
    if (!element) return;
    const top = values.indexOf(target) * ITEM;
    if (Math.abs(element.scrollTop - top) <= 1) return;
    picking.current = target;
    element.scrollTo({ top, behavior: 'smooth' });
  };

  // Человек взялся за колесо сам — тап больше не главный, промежуточные строки снова выбираются.
  const takeOver = () => {
    picking.current = null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const index = values.indexOf(value) + (event.key === 'ArrowUp' ? -1 : 1);
    onChange(values[Math.min(values.length - 1, Math.max(0, index))]);
  };

  return (
    <div
      ref={scroller}
      className="wheel"
      role="listbox"
      aria-label={label}
      tabIndex={0}
      onScroll={onScroll}
      onKeyDown={onKeyDown}
      onWheel={takeOver}
      onTouchStart={() => {
        held.current = true;
        takeOver();
      }}
      onTouchEnd={() => {
        held.current = false;
      }}
      onTouchCancel={() => {
        held.current = false;
      }}
    >
      {/* Пустые поля сверху и снизу нужны, чтобы первую и последнюю строку можно было поставить по центру. */}
      <div className="wheel__pad" aria-hidden="true" />
      {values.map((item) => (
        <div
          key={item}
          role="option"
          aria-selected={item === value}
          className={item === value ? 'wheel__item wheel__item--on' : 'wheel__item'}
          onClick={() => pick(item)}
        >
          {pad(item)}
        </div>
      ))}
      <div className="wheel__pad" aria-hidden="true" />
    </div>
  );
}

interface TimeFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}

/**
 * Время «как в айфоне»: строка со значением, по нажатию под ней раскрываются колёса
 * часов и минут. Печатать не нужно, поэтому нечего стирать и нельзя ввести неверное.
 */
export function TimeField({ label, value, onChange, hint }: TimeFieldProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const known = isValidTime(value);
  const [hours, minutes] = (known ? value : '09:00').split(':').map(Number);

  // Два колеса могут сдвинуться в одном кадре, до перерисовки. Поэтому время собираем из
  // последнего отданного значения, а не из значения прошлой отрисовки: иначе второе
  // колесо затрёт ход первого.
  const current = useRef(value);
  useEffect(() => {
    current.current = value;
  }, [value]);

  // Раскрытым бывает одно поле: два колеса подряд не помещаются в форму.
  useEffect(() => {
    const closeIfOther = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== id) setOpen(false);
    };
    window.addEventListener(OPENED, closeIfOther);
    return () => window.removeEventListener(OPENED, closeIfOther);
  }, [id]);

  const toggle = () => {
    if (!open) window.dispatchEvent(new CustomEvent(OPENED, { detail: id }));
    setOpen(!open);
  };

  const change = (part: 'hours' | 'minutes', next: number) => {
    const [h, m] = (isValidTime(current.current) ? current.current : '09:00').split(':').map(Number);
    const text = part === 'hours' ? `${pad(next)}:${pad(m)}` : `${pad(h)}:${pad(next)}`;
    current.current = text;
    onChange(text);
  };

  return (
    <div className="field">
      <Typography.Label variant="small">{label}</Typography.Label>
      <button
        type="button"
        className={known ? 'timefield__value' : 'timefield__value timefield__value--empty'}
        aria-expanded={open}
        aria-label={`${label}: ${known ? `${pad(hours)}:${pad(minutes)}` : 'не задано'}`}
        onClick={toggle}
      >
        <span>{known ? `${pad(hours)}:${pad(minutes)}` : '––:––'}</span>
        <span className="timefield__chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="timefield__panel">
          <Wheel label="Часы" values={HOURS} value={hours} onChange={(next) => change('hours', next)} />
          <span className="timefield__colon" aria-hidden="true">
            :
          </span>
          <Wheel label="Минуты" values={MINUTES} value={minutes} onChange={(next) => change('minutes', next)} />
        </div>
      )}
      {hint && (
        <Typography.Label variant="small" className="field__hint">
          {hint}
        </Typography.Label>
      )}
    </div>
  );
}

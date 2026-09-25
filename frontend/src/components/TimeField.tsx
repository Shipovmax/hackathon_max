import { Typography } from '@maxhub/max-ui';
import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';

import { isValidTime } from '../lib/format';

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

function Wheel({ label, values, value, onChange }: WheelProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const held = useRef(false);
  const loop = [...values, ...values, ...values];
  const shown = useRef<number | null>(null);
  const picking = useRef<number | null>(null);

  const moveTo = (target: number) => {
    const element = scroller.current;
    if (!element) return;
    const top = (values.length + Math.max(0, values.indexOf(target))) * ITEM;
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
      let rawIndex = Math.round(element.scrollTop / ITEM);
      const logicalIndex = ((rawIndex % values.length) + values.length) % values.length;
      if (rawIndex < values.length / 2 || rawIndex >= values.length * 2.5) {
        rawIndex = values.length + logicalIndex;
        element.scrollTop = rawIndex * ITEM;
      }
      const next = values[logicalIndex];
      if (next !== shown.current) {
        shown.current = next;
        onChange(next);
      }
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (picking.current !== null) {
        const target = picking.current;
        picking.current = null;
        moveTo(target);
        return;
      }
      if (!held.current && shown.current !== null) moveTo(shown.current);
    }, 140);
  };

  const pick = (target: number, renderedIndex: number) => {
    shown.current = target;
    onChange(target);
    const element = scroller.current;
    if (!element) return;
    const top = renderedIndex * ITEM;
    if (Math.abs(element.scrollTop - top) <= 1) return;
    picking.current = target;
    element.scrollTo({ top, behavior: 'smooth' });
  };

  const takeOver = () => {
    picking.current = null;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const step = event.key === 'ArrowUp' ? -1 : 1;
    const index = (values.indexOf(value) + step + values.length) % values.length;
    onChange(values[index]);
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
      <div className="wheel__pad" aria-hidden="true" />
      {loop.map((item, index) => {
        const accessible = index >= values.length && index < values.length * 2;
        return (
          <div
            key={`${index}-${item}`}
            role={accessible ? 'option' : undefined}
            aria-hidden={accessible ? undefined : true}
            aria-selected={accessible ? item === value : undefined}
            className={item === value ? 'wheel__item wheel__item--on' : 'wheel__item'}
            onClick={() => pick(item, index)}
          >
            {pad(item)}
          </div>
        );
      })}
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

export function TimeField({ label, value, onChange, hint }: TimeFieldProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const known = isValidTime(value);
  const [hours, minutes] = (known ? value : '09:00').split(':').map(Number);

  const current = useRef(value);
  useEffect(() => {
    current.current = value;
  }, [value]);

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

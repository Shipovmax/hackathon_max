import { IconButton, Typography } from '@maxhub/max-ui';

import { addDays, formatDate, today, weekdayIndex, WEEKDAYS } from '../lib/format';
import { Icon } from './Icon';

interface DateNavProps {
  date: string;
  onChange: (date: string) => void;
  /** Вперёд дальше сегодняшнего дня смотреть нечего: отметок там ещё нет. */
  maxDate?: string;
}

export function DateNav({ date, onChange, maxDate = today() }: DateNavProps) {
  const label = date === today() ? `Сегодня, ${formatDate(date)}` : `${WEEKDAYS[weekdayIndex(date)]}, ${formatDate(date)}`;

  return (
    <div className="datenav">
      <IconButton size="small" variant="secondary" aria-label="Предыдущий день" onClick={() => onChange(addDays(date, -1))}>
        <Icon name="back" />
      </IconButton>
      <button
        type="button"
        className="datenav__current"
        disabled={date === today()}
        aria-label={date === today() ? label : `${label}. Вернуться к сегодняшнему дню`}
        onClick={() => onChange(today())}
      >
        <Typography.Body variant="medium-strong">{label}</Typography.Body>
        {date !== today() && <span className="datenav__today">К сегодня</span>}
      </button>
      <IconButton
        size="small"
        variant="secondary"
        aria-label="Следующий день"
        disabled={date >= maxDate}
        onClick={() => onChange(addDays(date, 1))}
      >
        <Icon name="forward" />
      </IconButton>
    </div>
  );
}

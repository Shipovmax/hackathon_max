import { IconButton, Typography } from '@maxhub/max-ui';

import { addDays, formatDate, today, weekdayIndex, WEEKDAYS } from '../lib/format';
import { Icon } from './Icon';

interface DateNavProps {
  date: string;
  onChange: (date: string) => void;
  /** Последний день, до которого можно листать вперёд; null — без ограничения. */
  maxDate?: string | null;
  /** Дата становится кнопкой нативного календаря. */
  calendar?: boolean;
}

export function DateNav({ date, onChange, maxDate = today(), calendar = false }: DateNavProps) {
  const label = date === today() ? `Сегодня, ${formatDate(date)}` : `${WEEKDAYS[weekdayIndex(date)]}, ${formatDate(date)}`;

  return (
    <div className="datenav">
      <IconButton size="small" variant="secondary" aria-label="Предыдущий день" onClick={() => onChange(addDays(date, -1))}>
        <Icon name="back" />
      </IconButton>
      {calendar ? (
        <label className="datenav__calendar">
          <Typography.Body variant="medium-strong">{label}</Typography.Body>
          <Icon name="calendar" />
          <input
            type="date"
            value={date}
            max={maxDate ?? undefined}
            aria-label="Выбрать дату"
            onChange={(event) => event.target.value && onChange(event.target.value)}
          />
        </label>
      ) : (
        <Typography.Body variant="medium-strong">{label}</Typography.Body>
      )}
      <IconButton
        size="small"
        variant="secondary"
        aria-label="Следующий день"
        disabled={maxDate !== null && date >= maxDate}
        onClick={() => onChange(addDays(date, 1))}
      >
        <Icon name="forward" />
      </IconButton>
    </div>
  );
}

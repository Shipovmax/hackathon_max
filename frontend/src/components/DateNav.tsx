import { IconButton, Typography } from '@maxhub/max-ui';

import { addDays, formatDate, today, weekdayIndex, WEEKDAYS } from '../lib/format';
import { Icon } from './Icon';

interface DateNavProps {
  date: string;
  onChange: (date: string) => void;
  /** Последний день, до которого можно листать вперёд; null — без ограничения. */
  maxDate?: string | null;
}

export function DateNav({ date, onChange, maxDate = today() }: DateNavProps) {
  const label = date === today() ? `Сегодня, ${formatDate(date)}` : `${WEEKDAYS[weekdayIndex(date)]}, ${formatDate(date)}`;

  return (
    <div className="datenav">
      <IconButton size="small" variant="secondary" aria-label="Предыдущий день" onClick={() => onChange(addDays(date, -1))}>
        <Icon name="back" />
      </IconButton>
      <Typography.Body variant="medium-strong">{label}</Typography.Body>
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

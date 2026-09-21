import { Button, Typography } from '@maxhub/max-ui';

import { ApiError, describeError } from '../api/errors';
import { isInsideMax } from '../max/bridge';

interface AccessProblemProps {
  error: Error | null;
  onRetry: () => void;
  notOwner?: boolean;
}

/** Тупика быть не должно: всегда видно, что случилось и что делать дальше. */
export function AccessProblem({ error, onRetry, notOwner }: AccessProblemProps) {
  // describeError уже говорит, что делать, поэтому подсказку добавляем только там,
  // где повтор не поможет.
  let message = error ? describeError(error) : 'Не удалось загрузить данные.';
  let hint = '';
  let retry = true;

  if (notOwner || (error instanceof ApiError && error.status === 403)) {
    message = 'Приложение только для владельца сети.';
    hint = 'Вернитесь в чат с ботом и отправьте /role, чтобы выбрать роль владельца.';
    retry = false;
  } else if (error instanceof ApiError && error.status === 401) {
    message = 'Откройте приложение из чата с ботом в MAX.';
    hint = isInsideMax()
      ? 'Запуск устарел. Закройте приложение и откройте его из чата заново.'
      : 'В обычном браузере данные недоступны: приложение проверяет подпись запуска MAX.';
    retry = false;
  }

  return (
    <div className="center">
      <Typography.Title variant="small-strong">{message}</Typography.Title>
      {hint && <Typography.Body variant="medium">{hint}</Typography.Body>}
      {retry && <Button onClick={onRetry}>Повторить</Button>}
    </div>
  );
}

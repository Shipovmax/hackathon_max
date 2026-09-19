import { Button, Typography } from '@maxhub/max-ui';

import { ApiError } from '../api/errors';

export function AccessProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  let message = 'Не удалось загрузить данные.';
  let retry = true;

  if (error instanceof ApiError && error.status === 403 && error.code === 'not_owner') {
    message = 'Приложение только для владельцев. Вернитесь в чат с ботом и отправьте /role, чтобы выбрать роль.';
    retry = false;
  } else if (error instanceof ApiError && error.status === 401) {
    message = 'Откройте приложение из чата с ботом в MAX.';
    retry = false;
  }

  return (
    <div className="center">
      <Typography.Body>{message}</Typography.Body>
      {retry && <Button onClick={onRetry}>Повторить</Button>}
    </div>
  );
}

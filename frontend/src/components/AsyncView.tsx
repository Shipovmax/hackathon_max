import { Button, Spinner, Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

import { describeError } from '../api/errors';
import type { ApiState } from '../api/hooks';

interface AsyncViewProps<T> {
  state: ApiState<T>;
  children: (data: T) => ReactNode;
}

/** Загрузка, ошибка с причиной и повтор — на каждом экране одинаково. */
export function AsyncView<T>({ state, children }: AsyncViewProps<T>) {
  if (state.loading && state.data === null) {
    return (
      <div className="center">
        <Spinner />
        <Typography.Label variant="small">Загружаем данные</Typography.Label>
      </div>
    );
  }
  if (state.data === null) {
    return (
      <div className="center">
        <Typography.Body variant="medium">
          {state.error ? describeError(state.error) : 'Не удалось загрузить данные'}
        </Typography.Body>
        <Button onClick={state.reload} loading={state.loading}>
          Повторить
        </Button>
      </div>
    );
  }
  return <>{children(state.data)}</>;
}

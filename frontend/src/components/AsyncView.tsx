import { Button, Spinner, Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

import type { ApiState } from '../api/hooks';

interface AsyncViewProps<T> {
  state: ApiState<T>;
  children: (data: T) => ReactNode;
}

export function AsyncView<T>({ state, children }: AsyncViewProps<T>) {
  if (state.loading) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  if (state.error || state.data === null) {
    return (
      <div className="center">
        <Typography.Body>Не удалось загрузить данные</Typography.Body>
        <Button onClick={state.reload}>Повторить</Button>
      </div>
    );
  }
  return <>{children(state.data)}</>;
}

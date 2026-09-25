import { Button, Typography } from '@maxhub/max-ui';

import { describeError } from '../api/errors';

interface ErrorNoteProps {
  error: Error | null;
  onRetry?: () => void;
}

export function ErrorNote({ error, onRetry }: ErrorNoteProps) {
  if (!error) return null;
  return (
    <div className="alert alert--bad">
      <Typography.Body variant="medium">{describeError(error)}</Typography.Body>
      {onRetry && (
        <Button size="small" variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

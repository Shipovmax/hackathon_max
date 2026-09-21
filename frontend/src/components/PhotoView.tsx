import { Button, Spinner, Typography } from '@maxhub/max-ui';
import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { apiBlobUrl } from '../api/client';
import { describeError } from '../api/errors';
import { useBackButton } from '../max/bridge';

interface PhotoViewProps {
  url: string | null;
  title: string;
  onClose: () => void;
}

const isDirect = (url: string) => url.startsWith('data:') || url.startsWith('http');

/** Фото отметки во весь экран. Скачивание не нужно: владелец просто смотрит. */
export function PhotoView({ url, title, onClose }: PhotoViewProps) {
  const close = useCallback(() => onClose(), [onClose]);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useBackButton(url ? close : null);

  useEffect(() => {
    if (!url) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [url, close]);

  useEffect(() => {
    setSource(null);
    setError(null);
    if (!url) return;
    if (isDirect(url)) {
      setSource(url);
      return;
    }

    let objectUrl: string | null = null;
    let cancelled = false;
    apiBlobUrl(url).then(
      (created) => {
        objectUrl = created;
        if (cancelled) URL.revokeObjectURL(created);
        else setSource(created);
      },
      (failure: Error) => {
        if (!cancelled) setError(failure);
      },
    );
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, attempt]);

  if (!url) return null;

  return createPortal(
    <div className="photo" onClick={close} role="dialog" aria-label={title}>
      <div className="photo__body" onClick={(event) => event.stopPropagation()}>
        {source && <img className="photo__image" src={source} alt={title} />}
        {!source && !error && <Spinner />}
        {error && (
          <div className="center">
            <Typography.Body variant="medium">{describeError(error)}</Typography.Body>
            <Button size="small" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          </div>
        )}
      </div>
      <span className="photo__caption">{title}</span>
      <Button size="small" variant="overlay" onClick={close}>
        Закрыть
      </Button>
    </div>,
    document.body,
  );
}

import { Button, IconButton, Spinner, Typography } from '@maxhub/max-ui';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { apiBlobUrl } from '../api/client';
import { describeError } from '../api/errors';
import { useBackButton } from '../max/bridge';
import { Icon } from './Icon';

interface PhotoViewProps {
  url: string | null;
  title: string;
  onClose: () => void;
}

const isDirect = (url: string) => url.startsWith('data:') || url.startsWith('http');

/** Фото отметки во весь экран. Скачивание не нужно: владелец просто смотрит. */
export function PhotoView({ url, title, onClose }: PhotoViewProps) {
  const close = useCallback(() => onClose(), [onClose]);
  const panel = useRef<HTMLDivElement>(null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useBackButton(url ? close : null);

  useEffect(() => {
    if (!url) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    const frame = requestAnimationFrame(() => panel.current?.focus());
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
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
  const portalRoot = document.querySelector<HTMLElement>('.app-root') ?? document.body;

  return createPortal(
    <div className="photo" onClick={close}>
      <div
        ref={panel}
        className="photo__panel"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="photo__header">
          <Typography.Title variant="small-strong">Фото отчёта</Typography.Title>
          <IconButton size="small" variant="overlay" aria-label="Закрыть фото" onClick={close}>
            <Icon name="close" />
          </IconButton>
        </div>
        <div className="photo__body">
          {source && <img className="photo__image" src={source} alt={title} />}
          {!source && !error && <Spinner />}
          {error && (
            <div className="center">
              <Typography.Body variant="medium">{describeError(error)}</Typography.Body>
              <Button size="small" variant="overlay" onClick={() => setAttempt((n) => n + 1)}>
                Повторить
              </Button>
            </div>
          )}
        </div>
        <div className="photo__footer">
          <span className="photo__caption">{title}</span>
          <Button size="small" variant="overlay" onClick={close}>
            Закрыть
          </Button>
        </div>
      </div>
    </div>,
    portalRoot,
  );
}

import { Typography } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';

/** Ненавязчиво сообщает об офлайне; формы и уже загруженные данные остаются доступны. */
export function NetworkStatus() {
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const connected = () => setOnline(true);
    const disconnected = () => setOnline(false);
    window.addEventListener('online', connected);
    window.addEventListener('offline', disconnected);
    return () => {
      window.removeEventListener('online', connected);
      window.removeEventListener('offline', disconnected);
    };
  }, []);

  if (online) return null;
  return (
    <div className="network-note" role="status">
      <Typography.Label variant="small">Нет сети. Показываем последние загруженные данные.</Typography.Label>
    </div>
  );
}

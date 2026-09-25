import { IconButton, Typography } from '@maxhub/max-ui';
import { type ReactNode, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useBackButton } from '../max/bridge';
import { Icon } from './Icon';

interface ScreenProps {
  title: string;
  subtitle?: string;
  back?: boolean;
  backTo?: string;
  action?: ReactNode;
  children: ReactNode;
}

export function Screen({ title, subtitle, back, backTo = '/', action, children }: ScreenProps) {
  const navigate = useNavigate();
  const goBack = useCallback(() => {
    const historyIndex = window.history.state?.idx;
    if (typeof historyIndex === 'number' && historyIndex > 0) navigate(-1);
    else navigate(backTo, { replace: true });
  }, [backTo, navigate]);
  const goHome = useCallback(() => navigate('/'), [navigate]);
  useBackButton(back ? goBack : null);

  return (
    <div className="screen">
      <div className="screen__header">
        <div className="screen__heading">
          {back && (
            <nav className="screen__nav" aria-label="Навигация по приложению">
              <IconButton size="small" variant="secondary" aria-label="Назад" onClick={goBack}>
                <Icon name="back" />
              </IconButton>
              <IconButton
                size="small"
                variant="secondary"
                aria-label="На главную"
                title="На главную"
                onClick={goHome}
              >
                <Icon name="store" />
              </IconButton>
            </nav>
          )}
          <div className="screen__titles">
            {subtitle && (
              <Typography.Label variant="medium" className="screen__subtitle">
                {subtitle}
              </Typography.Label>
            )}
            <Typography.Title variant="large-strong" className="screen__title">
              {title}
            </Typography.Title>
          </div>
        </div>
        {action && <div className="screen__trailing">{action}</div>}
      </div>
      {children}
    </div>
  );
}

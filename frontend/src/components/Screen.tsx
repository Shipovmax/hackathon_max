import { Typography } from '@maxhub/max-ui';
import { type ReactNode, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useBackButton } from '../max/bridge';

interface ScreenProps {
  title: string;
  subtitle?: string;
  back?: boolean;
  children: ReactNode;
}

export function Screen({ title, subtitle, back, children }: ScreenProps) {
  const navigate = useNavigate();
  const goBack = useCallback(() => navigate(-1), [navigate]);
  useBackButton(back ? goBack : null);

  return (
    <div className="screen">
      <div className="screen__header">
        {subtitle && <Typography.Label variant="medium">{subtitle}</Typography.Label>}
        <Typography.Title variant="large-strong">{title}</Typography.Title>
      </div>
      {children}
    </div>
  );
}

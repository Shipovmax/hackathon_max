import { Button, Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

import { Icon } from './Icon';

interface EmptyProps {
  icon: 'store' | 'people' | 'calendar' | 'clock' | 'camera';
  title: string;
  text: string;
  action?: { label: string; onClick: () => void };
  children?: ReactNode;
}

/** Пустой экран объясняет, что здесь появится и что для этого сделать. */
export function Empty({ icon, title, text, action, children }: EmptyProps) {
  return (
    <div className="empty">
      <span className="empty__icon">
        <Icon name={icon} size={26} />
      </span>
      <Typography.Body variant="medium-strong">{title}</Typography.Body>
      <Typography.Label variant="small" className="muted">
        {text}
      </Typography.Label>
      {action && (
        <Button size="small" variant="secondary" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
      {children}
    </div>
  );
}

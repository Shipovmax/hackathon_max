import { Input, Switch, Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

import { formatDate } from '../lib/format';

interface FieldProps {
  label: string;
  hint?: string;
  children: ReactNode;
}

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="field">
      <Typography.Label variant="small">{label}</Typography.Label>
      {children}
      {hint && (
        <Typography.Label variant="small" className="field__hint">
          {hint}
        </Typography.Label>
      )}
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  inputMode?: 'text' | 'numeric';
}

export function TextField({ label, value, onChange, placeholder, hint, inputMode }: TextFieldProps) {
  return (
    <Field label={label} hint={hint}>
      <Input
        value={value}
        placeholder={placeholder}
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

interface DateFieldProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Дата разовой задачи. Нативный `input[type=date]` в мобильном MAX выглядит как
 * блёклая строчка, поэтому подписываем выбранную дату по-русски рядом с полем.
 */
export function DateField({ value, onChange }: DateFieldProps) {
  return (
    <div className="datefield">
      <input
        className="datefield__input"
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="datefield__label">{value ? formatDate(value) : 'дата не выбрана'}</span>
    </div>
  );
}

interface SwitchFieldProps {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function SwitchField({ label, hint, checked, onChange }: SwitchFieldProps) {
  return (
    <label className="field field--row">
      <span className="field__text">
        <Typography.Body variant="medium">{label}</Typography.Body>
        {hint && <Typography.Label variant="small">{hint}</Typography.Label>}
      </span>
      <Switch checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

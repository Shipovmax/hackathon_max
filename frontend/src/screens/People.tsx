import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';

import { apiPost } from '../api/client';
import { useAction, useApi } from '../api/hooks';
import type { Person, StoreInput, StoreWithPeople } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Empty } from '../components/Empty';
import { Icon } from '../components/Icon';
import { ErrorNote } from '../components/ErrorNote';
import { TextField } from '../components/Field';
import { TimeField } from '../components/TimeField';
import { Screen } from '../components/Screen';
import { Sheet } from '../components/Sheet';
import { useToast } from '../components/Toast';
import { formatRange, isValidTime, minutesOf, plural } from '../lib/format';

const STATUS: Record<Person['status'], string> = {
  connected: 'в боте',
  invited: 'ждёт привязки',
  dismissed: 'уволен',
};

export function People() {
  const state = useApi<StoreWithPeople[]>('/stores/');
  const [newStore, setNewStore] = useState(false);
  const [newEmployeeAt, setNewEmployeeAt] = useState<StoreWithPeople | null>(null);
  const [person, setPerson] = useState<{ store: StoreWithPeople; person: Person } | null>(null);

  return (
    <AsyncView state={state}>
      {(stores) => {
        const employees = stores.reduce(
          (sum, store) => sum + store.employees.filter((person) => person.status !== 'dismissed').length,
          0,
        );
        return (
          <Screen
            title="Точки и сотрудники"
            subtitle={`${stores.length} ${plural(stores.length, ['точка', 'точки', 'точек'])} · ${employees} ${plural(employees, ['сотрудник', 'сотрудника', 'сотрудников'])}`}
            back
            backTo="/"
          >
            {stores.length === 0 && (
              <div className="screen__block">
                <Empty
                  icon="store"
                  title="Магазинов пока нет"
                  text="Начните с точки: название, адрес и часы работы. Потом добавьте людей и выдайте им коды."
                />
              </div>
            )}

            {stores.map((store) => (
              <CellList
                key={store.id}
                className="people__store"
                mode="island"
                header={
                  <CellHeader after={<span className="muted">{formatRange(store.open_time, store.close_time)}</span>}>
                    {store.name}
                  </CellHeader>
                }
              >
                {store.employees.length === 0 && (
                  <CellSimple title="Сотрудников пока нет" subtitle="Бот не сможет вести смену без людей" />
                )}
                {store.employees.map((employee) => (
                  <CellSimple
                    key={employee.id}
                    height="compact"
                    title={employee.name}
                    subtitle={
                      employee.status === 'invited' && employee.invite_code
                        ? `код ${employee.invite_code}`
                        : undefined
                    }
                    after={
                      <span
                        className={`badge badge--${employee.status === 'connected' ? 'ok' : employee.status === 'invited' ? 'warn' : 'idle'}`}
                      >
                        {STATUS[employee.status]}
                      </span>
                    }
                    showChevron
                    onClick={() => setPerson({ store, person: employee })}
                  />
                ))}
                <CellSimple
                  height="compact"
                  before={<Icon name="plus" />}
                  title="Добавить сотрудника"
                  onClick={() => setNewEmployeeAt(store)}
                />
              </CellList>
            ))}

            <div className="screen__block">
              <Button variant="secondary" stretched onClick={() => setNewStore(true)}>
                Добавить точку
              </Button>
            </div>

            <StoreForm
              open={newStore}
              onClose={() => setNewStore(false)}
              onDone={() => {
                setNewStore(false);
                state.reload();
              }}
            />
            <EmployeeForm
              store={newEmployeeAt}
              onClose={() => setNewEmployeeAt(null)}
              onDone={() => {
                setNewEmployeeAt(null);
                state.reload();
              }}
            />
            <PersonCard
              data={person}
              onClose={() => setPerson(null)}
              onDone={() => {
                setPerson(null);
                state.reload();
              }}
            />
          </Screen>
        );
      }}
    </AsyncView>
  );
}

function StoreForm({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const save = useAction();
  const [form, setForm] = useState<StoreInput>({ name: '', address: '', open_time: '10:00', close_time: '22:00' });
  const [problem, setProblem] = useState<string | null>(null);
  const patch = (fields: Partial<StoreInput>) => {
    setForm((current) => ({ ...current, ...fields }));
    setProblem(null);
    save.reset();
  };

  const submit = async () => {
    if (form.name.trim().length < 2) {
      setProblem('Введите название точки');
      return;
    }
    if (!isValidTime(form.open_time) || !isValidTime(form.close_time)) {
      setProblem('Время работы в формате ЧЧ:ММ');
      return;
    }
    if (minutesOf(form.open_time) >= minutesOf(form.close_time)) {
      setProblem('Закрытие должно быть позже открытия');
      return;
    }
    const result = await save.run(() => apiPost<StoreWithPeople>('/stores/', { ...form, name: form.name.trim() }));
    if (!result) return;
    toast.show('Точка добавлена');
    setForm({ name: '', address: '', open_time: '10:00', close_time: '22:00' });
    setProblem(null);
    onDone();
  };

  return (
    <Sheet
      title="Новая точка"
      open={open}
      onClose={onClose}
      actions={
        <Button stretched loading={save.running} onClick={submit}>
          Добавить точку
        </Button>
      }
    >
      <TextField label="Название" value={form.name} onChange={(name) => patch({ name })} placeholder="Ленина, 14" />
      <TextField label="Адрес" value={form.address} onChange={(address) => patch({ address })} placeholder="ул. Ленина, 14" />
      <TimeField label="Открытие" value={form.open_time} onChange={(open_time) => patch({ open_time })} />
      <TimeField label="Закрытие" value={form.close_time} onChange={(close_time) => patch({ close_time })} />
      {problem && <div className="alert alert--bad" role="alert">{problem}</div>}
      <ErrorNote error={save.error} />
    </Sheet>
  );
}

function EmployeeForm({ store, onClose, onDone }: { store: StoreWithPeople | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const save = useAction();
  const [name, setName] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  if (!store) return null;

  const changeName = (value: string) => {
    setName(value);
    setProblem(null);
    save.reset();
  };

  const submit = async () => {
    if (name.trim().length < 2) {
      setProblem('Введите имя сотрудника');
      return;
    }
    const result = await save.run(() => apiPost<Person>(`/stores/${store.id}/employees/`, { name: name.trim() }));
    if (!result) return;
    toast.show(result.invite_code ? `Код приглашения: ${result.invite_code}` : 'Сотрудник добавлен');
    setName('');
    setProblem(null);
    onDone();
  };

  return (
    <Sheet
      title={`Сотрудник · ${store.name}`}
      open
      onClose={onClose}
      actions={
        <Button stretched loading={save.running} onClick={submit}>
          Добавить
        </Button>
      }
    >
      <TextField label="Имя" value={name} onChange={changeName} placeholder="Анна К." hint="После добавления появится код приглашения — передайте его человеку" />
      {problem && <div className="alert alert--bad" role="alert">{problem}</div>}
      <ErrorNote error={save.error} />
    </Sheet>
  );
}

function PersonCard({
  data,
  onClose,
  onDone,
}: {
  data: { store: StoreWithPeople; person: Person } | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const invite = useAction();
  const dismiss = useAction();
  const [confirm, setConfirm] = useState(false);
  const [code, setCode] = useState<string | null>(null);

  if (!data) return null;
  const { person } = data;
  const shownCode = code ?? person.invite_code;

  // Код владелец передаёт человеку в переписке, поэтому копирование важнее вида.
  const copy = async (value: string) => {
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(value);
      else {
        const fallback = document.createElement('textarea');
        try {
          fallback.value = value;
          fallback.setAttribute('readonly', '');
          fallback.style.position = 'fixed';
          fallback.style.opacity = '0';
          document.body.appendChild(fallback);
          fallback.select();
          if (!document.execCommand('copy')) throw new Error('copy failed');
        } finally {
          fallback.remove();
        }
      }
      toast.show('Код скопирован');
    } catch {
      toast.show('Не удалось скопировать, введите код вручную', 'bad');
    }
  };

  const runInvite = async () => {
    const result = await invite.run(() => apiPost<Person>(`/employees/${person.id}/invite/`));
    if (!result) return;
    setCode(result.invite_code);
    toast.show('Новый код выдан');
  };

  const runDismiss = async () => {
    const result = await dismiss.run(() => apiPost<Person>(`/employees/${person.id}/dismiss/`));
    if (!result) return;
    toast.show('Сотрудник деактивирован');
    onDone();
  };

  return (
    <Sheet
      title={person.name}
      open
      onClose={() => { setCode(null); setConfirm(false); onClose(); }}
      actions={
        person.status !== 'dismissed' && (
          <>
            <Button variant="secondary" stretched loading={invite.running} onClick={runInvite}>
              {shownCode ? 'Выдать новый код' : 'Выдать код приглашения'}
            </Button>
            {confirm ? (
              <Button variant="destructive" stretched loading={dismiss.running} onClick={runDismiss}>
                Точно деактивировать
              </Button>
            ) : (
              <Button variant="secondary" stretched onClick={() => setConfirm(true)}>
                Сотрудник уволен
              </Button>
            )}
          </>
        )
      }
    >
      <Typography.Body variant="medium">
        {person.status === 'connected'
          ? 'Аккаунт MAX привязан, бот шлёт задачи.'
          : person.status === 'invited'
            ? 'Пока не привязан. Передайте код — сотрудник отправит его боту.'
            : 'Уволен. История его отметок сохраняется.'}
      </Typography.Body>

      {shownCode && person.status !== 'dismissed' && (
        <button type="button" className="code" aria-label={`Скопировать код ${shownCode}`} onClick={() => copy(shownCode)}>
          <span className="code__value">{shownCode}</span>
          <span className="code__hint">
            <Icon name="copy" size={14} /> код одноразовый, нажмите чтобы скопировать
          </span>
        </button>
      )}

      <ErrorNote error={invite.error ?? dismiss.error} />
    </Sheet>
  );
}

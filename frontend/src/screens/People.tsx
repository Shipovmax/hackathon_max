import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';

import { apiPost } from '../api/client';
import { useAction, useApi } from '../api/hooks';
import type { Person, StoreInput, StoreWithPeople } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { ErrorNote } from '../components/ErrorNote';
import { TextField } from '../components/Field';
import { Screen } from '../components/Screen';
import { Sheet } from '../components/Sheet';
import { useToast } from '../components/Toast';
import { formatRange, isValidTime, normalizeTime } from '../lib/format';

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
      {(stores) => (
        <Screen
          title="Точки и сотрудники"
          subtitle={`${stores.length} точек · ${stores.reduce((sum, store) => sum + store.employees.filter((p) => p.status !== 'dismissed').length, 0)} сотрудников`}
          back
        >
          {stores.map((store) => (
            <CellList
              key={store.id}
              mode="island"
              header={
                <CellHeader after={<span className="muted">{formatRange(store.open_time, store.close_time)}</span>}>
                  {store.name}
                </CellHeader>
              }
            >
              {store.employees.length === 0 && <CellSimple title="Сотрудников пока нет" />}
              {store.employees.map((employee) => (
                <CellSimple
                  key={employee.id}
                  title={employee.name}
                  subtitle={employee.status === 'invited' && employee.invite_code ? `код ${employee.invite_code}` : undefined}
                  after={<span className={`badge badge--${employee.status === 'connected' ? 'ok' : employee.status === 'invited' ? 'warn' : 'idle'}`}>{STATUS[employee.status]}</span>}
                  showChevron
                  onClick={() => setPerson({ store, person: employee })}
                />
              ))}
              <CellSimple title="Добавить сотрудника" showChevron onClick={() => setNewEmployeeAt(store)} />
            </CellList>
          ))}

          <div className="screen__block">
            <Button variant="secondary" stretched onClick={() => setNewStore(true)}>
              Добавить точку
            </Button>
          </div>

          <StoreForm open={newStore} onClose={() => setNewStore(false)} onDone={() => { setNewStore(false); state.reload(); }} />
          <EmployeeForm
            store={newEmployeeAt}
            onClose={() => setNewEmployeeAt(null)}
            onDone={() => { setNewEmployeeAt(null); state.reload(); }}
          />
          <PersonCard
            data={person}
            onClose={() => setPerson(null)}
            onDone={() => { setPerson(null); state.reload(); }}
          />
        </Screen>
      )}
    </AsyncView>
  );
}

function StoreForm({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const save = useAction();
  const [form, setForm] = useState<StoreInput>({ name: '', address: '', open_time: '10:00', close_time: '22:00' });
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async () => {
    if (form.name.trim().length < 2) {
      setProblem('Введите название точки');
      return;
    }
    if (!isValidTime(form.open_time) || !isValidTime(form.close_time)) {
      setProblem('Время работы в формате ЧЧ:ММ');
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
    <Sheet title="Новая точка" open={open} onClose={onClose}>
      <TextField label="Название" value={form.name} onChange={(name) => setForm({ ...form, name })} placeholder="Ленина, 14" />
      <TextField label="Адрес" value={form.address} onChange={(address) => setForm({ ...form, address })} placeholder="ул. Ленина, 14" />
      <TextField label="Открытие" value={form.open_time} onChange={(value) => setForm({ ...form, open_time: normalizeTime(value) })} inputMode="numeric" />
      <TextField label="Закрытие" value={form.close_time} onChange={(value) => setForm({ ...form, close_time: normalizeTime(value) })} inputMode="numeric" />
      {problem && <div className="alert alert--bad">{problem}</div>}
      <ErrorNote error={save.error} />
      <Button stretched loading={save.running} onClick={submit}>
        Добавить точку
      </Button>
    </Sheet>
  );
}

function EmployeeForm({ store, onClose, onDone }: { store: StoreWithPeople | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const save = useAction();
  const [name, setName] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  if (!store) return null;

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
    <Sheet title={`Сотрудник · ${store.name}`} open onClose={onClose}>
      <TextField label="Имя" value={name} onChange={setName} placeholder="Анна К." hint="После добавления появится код приглашения — передайте его человеку" />
      {problem && <div className="alert alert--bad">{problem}</div>}
      <ErrorNote error={save.error} />
      <Button stretched loading={save.running} onClick={submit}>
        Добавить
      </Button>
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
    <Sheet title={person.name} open onClose={() => { setCode(null); setConfirm(false); onClose(); }}>
      <Typography.Body variant="medium">
        {person.status === 'connected'
          ? 'Аккаунт MAX привязан, бот шлёт задачи.'
          : person.status === 'invited'
            ? 'Пока не привязан. Передайте код — сотрудник отправит его боту.'
            : 'Уволен. История его отметок сохраняется.'}
      </Typography.Body>

      {shownCode && person.status !== 'dismissed' && (
        <div className="code">
          <Typography.Title variant="small-strong">{shownCode}</Typography.Title>
          <Typography.Label variant="small">код одноразовый</Typography.Label>
        </div>
      )}

      <ErrorNote error={invite.error ?? dismiss.error} />

      {person.status !== 'dismissed' && (
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
      )}
    </Sheet>
  );
}

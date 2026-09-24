import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';

import { apiDelete, apiPatch, apiPost } from '../api/client';
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
import { formatBusinessHours, isValidTime, minutesOf, plural, WEEKDAYS } from '../lib/format';

const STATUS: Record<Person['status'], string> = {
  connected: 'в боте',
  invited: 'ждёт привязки',
  dismissed: 'уволен',
};

export function People() {
  const state = useApi<StoreWithPeople[]>('/stores/');
  // Форма точки: 'new' — новая, объект — правка уже созданной.
  const [storeForm, setStoreForm] = useState<StoreWithPeople | 'new' | null>(null);
  const [newEmployeeAt, setNewEmployeeAt] = useState<StoreWithPeople | null>(null);
  const [person, setPerson] = useState<{ store: StoreWithPeople; person: Person } | null>(null);

  return (
    <AsyncView state={state}>
      {(stores) => {
        const employeeCount = stores.reduce(
          (sum, store) => sum + store.employees.filter((person) => person.status !== 'dismissed').length,
          0,
        );
        return (
        <Screen
          title="Точки и сотрудники"
          subtitle={`${stores.length} ${plural(stores.length, ['точка', 'точки', 'точек'])} · ${employeeCount} ${plural(employeeCount, ['сотрудник', 'сотрудника', 'сотрудников'])}`}
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
                <CellHeader after={<span className="muted">{formatBusinessHours(store.open_time, store.close_time)}</span>}>
                  {store.name}
                </CellHeader>
              }
            >
              <CellSimple
                height="compact"
                before={<Icon name="clock" />}
                title="Часы работы и выходные"
                subtitle={`${formatBusinessHours(store.open_time, store.close_time)} · ${daysOffLabel(store.closed_weekdays)}`}
                showChevron
                onClick={() => setStoreForm(store)}
              />
              {store.employees.length === 0 && (
                <CellSimple title="Сотрудников пока нет" subtitle="Бот не сможет вести смену без людей" />
              )}
              {store.employees.map((employee) => (
                <CellSimple
                  key={employee.id}
                  height="compact"
                  title={employee.name}
                  subtitle={employee.status === 'invited' && employee.invite_code ? `код ${employee.invite_code}` : undefined}
                  after={<span className={`badge badge--${employee.status === 'connected' ? 'ok' : employee.status === 'invited' ? 'warn' : 'idle'}`}>{STATUS[employee.status]}</span>}
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
            <Button variant="secondary" stretched onClick={() => setStoreForm('new')}>
              Добавить точку
            </Button>
          </div>

          <StoreForm store={storeForm} onClose={() => setStoreForm(null)} onDone={() => { setStoreForm(null); state.reload(); }} />
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
        );
      }}
    </AsyncView>
  );
}

const BLANK_STORE: StoreInput = { name: '', address: '', open_time: '10:00', close_time: '22:00', closed_weekdays: [] };

/** «выходные: сб, вс» — подпись под часами работы точки. */
function daysOffLabel(days: number[]): string {
  return days.length ? `выходные: ${days.map((day) => WEEKDAYS[day]).join(', ')}` : 'без выходных';
}

/**
 * Точка: и новая, и уже созданная. Часы работы и выходные меняются со временем —
 * летний график, новый выходной, — поэтому форма одна на оба случая.
 */
function StoreForm({
  store,
  onClose,
  onDone,
}: {
  store: StoreWithPeople | 'new' | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const save = useAction();
  const [form, setForm] = useState<StoreInput>(BLANK_STORE);
  const [problem, setProblem] = useState<string | null>(null);
  const existing = store && store !== 'new' ? store : null;
  const alwaysOpen = form.open_time === '00:00' && (form.close_time === '00:00' || form.close_time === '23:59');

  useEffect(() => {
    if (!store) return;
    setForm(
      store === 'new'
        ? BLANK_STORE
        : {
            name: store.name,
            address: store.address,
            open_time: store.open_time,
            close_time: store.close_time === '23:59' ? '00:00' : store.close_time,
            closed_weekdays: store.closed_weekdays,
          },
    );
    setProblem(null);
  }, [store]);

  const toggleDay = (day: number) =>
    setForm({
      ...form,
      closed_weekdays: form.closed_weekdays.includes(day)
        ? form.closed_weekdays.filter((item) => item !== day)
        : [...form.closed_weekdays, day].sort(),
    });

  const submit = async () => {
    if (form.name.trim().length < 2) {
      setProblem('Введите название точки');
      return;
    }
    if (!isValidTime(form.open_time) || !isValidTime(form.close_time)) {
      setProblem('Время работы в формате ЧЧ:ММ');
      return;
    }
    const closeTime = form.close_time === '00:00' ? '23:59' : form.close_time;
    if (minutesOf(closeTime) <= minutesOf(form.open_time)) {
      setProblem('Магазин должен закрываться позже, чем открывается');
      return;
    }
    if (form.closed_weekdays.length === 7) {
      setProblem('Точка не может быть закрыта всю неделю');
      return;
    }
    const body = { ...form, name: form.name.trim(), close_time: closeTime };
    const result = await save.run(() =>
      existing
        ? apiPatch<StoreWithPeople>(`/stores/${existing.id}/`, body)
        : apiPost<StoreWithPeople>('/stores/', body),
    );
    if (!result) return;
    toast.show(existing ? 'Точка сохранена' : 'Точка добавлена');
    onDone();
  };

  return (
    <Sheet title={existing ? existing.name : 'Новая точка'} open={Boolean(store)} onClose={onClose}>
      <TextField label="Название" value={form.name} onChange={(name) => setForm({ ...form, name })} placeholder="Ленина, 14" />
      <TextField label="Адрес" value={form.address} onChange={(address) => setForm({ ...form, address })} placeholder="ул. Ленина, 14" />
      <label className="field field--row">
        <span className="field__text">
          <Typography.Label variant="small">Круглосуточно</Typography.Label>
          <Typography.Label variant="small" className="field__hint">Без закрытия между сменами</Typography.Label>
        </span>
        <input
          type="checkbox"
          className="switch"
          checked={alwaysOpen}
          onChange={(event) =>
            setForm({
              ...form,
              open_time: event.target.checked ? '00:00' : '10:00',
              close_time: event.target.checked ? '00:00' : '22:00',
            })
          }
        />
      </label>
      {!alwaysOpen && (
        <>
          <TimeField label="Открытие" value={form.open_time} onChange={(open_time) => setForm({ ...form, open_time })} />
          <TimeField
            label="Закрытие"
            value={form.close_time}
            onChange={(close_time) => setForm({ ...form, close_time })}
            hint="00:00 означает закрытие в полночь"
          />
        </>
      )}
      <div className="field">
        <Typography.Label variant="small">Выходные точки</Typography.Label>
        <div className="weekdays" role="group" aria-label="Выходные точки">
          {WEEKDAYS.map((label, day) => (
            <button
              key={label}
              type="button"
              className={form.closed_weekdays.includes(day) ? 'weekday weekday--off' : 'weekday'}
              aria-pressed={form.closed_weekdays.includes(day)}
              onClick={() => toggleDay(day)}
            >
              {label}
            </button>
          ))}
        </div>
        <Typography.Label variant="small" className="field__hint">
          В выходной задачи не ставятся, а пустой день в графике не считается окном
        </Typography.Label>
      </div>
      {problem && <div className="alert alert--bad">{problem}</div>}
      <ErrorNote error={save.error} />
      <Button stretched loading={save.running} onClick={submit}>
        {existing ? 'Сохранить' : 'Добавить точку'}
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
  const remove = useAction();
  const [confirm, setConfirm] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [code, setCode] = useState<string | null>(null);

  if (!data) return null;
  const { person } = data;
  const shownCode = code ?? person.invite_code;

  // Код владелец передаёт человеку в переписке, поэтому копирование важнее вида.
  const copy = (value: string) => {
    navigator.clipboard?.writeText(value).then(
      () => toast.show('Код скопирован'),
      () => toast.show('Не удалось скопировать, введите код вручную', 'bad'),
    );
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

  const runRemove = async () => {
    const result = await remove.run(() => apiDelete(`/employees/${person.id}/`));
    if (result === undefined) return;
    toast.show('Сотрудник убран из списка');
    onDone();
  };

  return (
    <Sheet
      title={person.name}
      open
      onClose={() => {
        setCode(null);
        setConfirm(false);
        setConfirmRemove(false);
        onClose();
      }}
    >
      <Typography.Body variant="medium">
        {person.status === 'connected'
          ? 'Аккаунт MAX привязан, бот шлёт задачи.'
          : person.status === 'invited'
            ? 'Пока не привязан. Передайте код — сотрудник отправит его боту.'
            : 'Уволен. История его отметок сохраняется.'}
      </Typography.Body>

      {shownCode && person.status !== 'dismissed' && (
        <button type="button" className="code" onClick={() => copy(shownCode)}>
          <span className="code__value">{shownCode}</span>
          <span className="code__hint">
            <Icon name="copy" size={14} /> код одноразовый, нажмите чтобы скопировать
          </span>
        </button>
      )}

      <ErrorNote error={invite.error ?? dismiss.error ?? remove.error} />

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

      {person.status === 'dismissed' &&
        (confirmRemove ? (
          <Button variant="destructive" stretched loading={remove.running} onClick={runRemove}>
            Точно убрать из списка
          </Button>
        ) : (
          <Button variant="secondary" stretched onClick={() => setConfirmRemove(true)}>
            Убрать из списка
          </Button>
        ))}
    </Sheet>
  );
}

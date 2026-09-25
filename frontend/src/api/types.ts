export type TaskStatus =
  | 'scheduled'
  | 'reminded'
  | 'awaiting_photo'
  | 'done_on_time'
  | 'done_late'
  | 'overdue'
  | 'unclaimed'
  | 'missed';

export type StoreHealth = 'ok' | 'late' | 'overdue' | 'unclaimed';

export interface Me {
  max_user_id: number;
  first_name: string;
  role: 'owner' | 'employee' | '';
  network: { id: number; name: string } | null;
}

export interface DashboardStore {
  id: number;
  name: string;
  done: number;
  total: number;
  health: StoreHealth;
  last_event_label: string | null;
}

export interface Dashboard {
  date: string;
  stores: DashboardStore[];
}

export interface DayTask {
  id: number;
  template_id: number;
  title: string;
  planned_time: string;
  available_from: string;
  kind: 'daily' | 'one_time';
  status: TaskStatus;
  late_minutes: number | null;
  done_by: string | null;
  done_at: string | null;
  claimed_by: string | null;
  photo_url: string | null;
}

export interface StoreDay {
  store: { id: number; name: string };
  date: string;
  closed: boolean;
  on_shift: { name: string; start: string; end: string }[];
  tasks: DayTask[];
}

export interface ShiftInput {
  employee_id: number;
  date: string;
  start: string;
  end: string;
}

export interface Gap {
  date: string;
  start: string;
  end: string;
}

export interface Schedule {
  week_start: string;
  status: 'draft' | 'published';
  open_time: string;
  close_time: string;
  closed_weekdays: number[];
  employees: { id: number; name: string }[];
  shifts: ShiftInput[];
  gaps: Gap[];
}

export interface ScheduleDraft {
  week_start: string;
  shifts: ShiftInput[];
}

export interface Coverage {
  gaps: Gap[];
}

export interface TaskTemplateItem {
  id: number;
  title: string;
  kind: 'daily' | 'one_time';
  planned_time: string;
  available_from: string;
  on_date: string | null;
  tolerance_minutes: number;
  requires_photo: boolean;
  requires_claim: boolean;
}

export type TaskTemplateInput = Omit<TaskTemplateItem, 'id'>;

export interface Person {
  id: number;
  name: string;
  status: 'connected' | 'invited' | 'dismissed';
  invite_code: string | null;
}

export interface StoreWithPeople {
  id: number;
  name: string;
  address: string;
  open_time: string;
  close_time: string;
  closed_weekdays: number[];
  employees: Person[];
}

export type StoreInput = Pick<StoreWithPeople, 'name' | 'address' | 'open_time' | 'close_time' | 'closed_weekdays'>;

export interface EmployeeInput {
  name: string;
}

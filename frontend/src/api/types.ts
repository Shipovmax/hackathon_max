// Draft contract, mirrors backend/apps/api/urls.py. Times are "HH:MM", dates are "YYYY-MM-DD".

export type TaskStatus =
  | 'scheduled'
  | 'reminded'
  | 'awaiting_photo'
  | 'done_on_time'
  | 'done_late'
  | 'overdue'
  | 'unclaimed'
  | 'missed';

export type StoreHealth = 'ok' | 'overdue' | 'unclaimed';

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
  title: string;
  planned_time: string;
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
  on_shift: { name: string; start: string; end: string }[];
  tasks: DayTask[];
}

export interface Schedule {
  week_start: string;
  status: 'draft' | 'published';
  employees: { id: number; name: string }[];
  shifts: { employee_id: number; date: string; start: string; end: string }[];
  gaps: { date: string; start: string; end: string }[];
}

export interface TaskTemplateItem {
  id: number;
  title: string;
  kind: 'daily' | 'one_time';
  planned_time: string;
  on_date: string | null;
  tolerance_minutes: number;
  requires_photo: boolean;
  requires_claim: boolean;
}

export interface Person {
  id: number;
  name: string;
  status: 'connected' | 'invited' | 'dismissed';
}

export interface StoreWithPeople {
  id: number;
  name: string;
  address: string;
  employees: Person[];
}

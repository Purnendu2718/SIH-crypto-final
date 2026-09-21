-- ==============================================================================
-- CryptoTrace Sentinel — Initial Supabase Database Migration
-- Reference: SIH26183, Ministry of Home Affairs / I4C
-- ==============================================================================

-- Enable UUID extension if not already enabled
create extension if not exists "uuid-ossp";

-- 1. profiles: one row per officer, keyed to Supabase auth.users
create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  badge_no text,
  role text not null check (role in ('INVESTIGATOR','SUPERVISOR','ADMIN')),
  district text,
  created_at timestamptz default now()
);

-- 2. cases: cybercrime complaints / FIR records
create table if not exists cases (
  case_id uuid primary key default gen_random_uuid(),
  ncrp_ref text,
  victim_utr text,
  amount_inr numeric,
  assigned_officer_id uuid references profiles(id),
  status text default 'OPEN',
  created_at timestamptz default now()
);

-- 3. wallet_submissions: suspect crypto addresses submitted for analysis
create table if not exists wallet_submissions (
  submission_id uuid primary key default gen_random_uuid(),
  case_id uuid references cases(case_id) on delete cascade,
  chain text not null,
  address text not null,
  submitted_at timestamptz default now()
);

-- 4. analysis_runs: multi-hop trace execution sessions
create table if not exists analysis_runs (
  run_id uuid primary key default gen_random_uuid(),
  submission_id uuid references wallet_submissions(submission_id) on delete cascade,
  status text default 'PENDING',
  started_at timestamptz default now(),
  completed_at timestamptz
);

-- 5. trace_paths: individual transaction hops discovered during trace
create table if not exists trace_paths (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id) on delete cascade,
  hop_index int,
  from_addr text,
  to_addr text,
  tx_hash text,
  chain text,
  value numeric
);

-- 6. attributions: exchange / VASP attribution and confidence scoring
create table if not exists attributions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id) on delete cascade,
  matched_entity text,
  rule_fired text,
  confidence numeric,
  score_breakdown jsonb
);

-- 7. typologies_detected: money-laundering behavior patterns
create table if not exists typologies_detected (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id) on delete cascade,
  typology text,
  hop_start int,
  hop_end int
);

-- 8. evidence_packages: court-ready serialized evidence and hashes
create table if not exists evidence_packages (
  package_id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id) on delete cascade,
  sha256_hash text,
  merkle_root text,
  generated_at timestamptz default now()
);

-- 9. audit_log: tamper-evident, hash-chained activity audit log
create table if not exists audit_log (
  entry_id uuid primary key default gen_random_uuid(),
  prev_hash text,
  entry_hash text,
  officer_id uuid references profiles(id),
  action text,
  target_id text,
  timestamp timestamptz default now()
);

-- 10. vasp_directory: FIU-IND registered and known exchanges
create table if not exists vasp_directory (
  entity_name text primary key,
  chain text,
  hot_wallet_addresses text[],
  fiu_ind_registered boolean default false,
  sla_hours numeric default 24,
  nodal_contact text
);

-- 11. watchlist_entries: golden hour monitoring alerts
create table if not exists watchlist_entries (
  id uuid primary key default gen_random_uuid(),
  address text not null,
  chain text not null,
  case_id uuid references cases(case_id) on delete cascade,
  alert_channel text
);

-- 12. intel_tags: anonymized hash-based inter-agency police intel exchange
create table if not exists intel_tags (
  address_hash text primary key,
  tag text not null,
  district text not null,
  submitted_by uuid references profiles(id),
  submitted_at timestamptz default now()
);

-- ==============================================================================
-- Automatic Profile Creation Trigger on Supabase Auth Signup
-- ==============================================================================
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, full_name, badge_no, role, district)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', 'Officer'),
    coalesce(new.raw_user_meta_data->>'badge_no', 'N/A'),
    coalesce(new.raw_user_meta_data->>'role', 'INVESTIGATOR'),
    coalesce(new.raw_user_meta_data->>'district', 'Central')
  );
  return new;
end;
$$ language plpgsql security definer;

-- Trigger definition
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ==============================================================================
-- Row Level Security (RLS) Policies
-- ==============================================================================

-- Enable RLS on all tables
alter table profiles enable row level security;
alter table cases enable row level security;
alter table wallet_submissions enable row level security;
alter table analysis_runs enable row level security;
alter table trace_paths enable row level security;
alter table attributions enable row level security;
alter table typologies_detected enable row level security;
alter table evidence_packages enable row level security;
alter table audit_log enable row level security;
alter table vasp_directory enable row level security;
alter table watchlist_entries enable row level security;
alter table intel_tags enable row level security;

-- Profiles: Officers read own profile; Supervisors & Admins read all
create policy profiles_select_policy on profiles
  for select using (
    id = auth.uid()
    or exists (select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN'))
  );

-- Cases: Investigators read own cases; Supervisors & Admins read all
create policy investigator_own_cases on cases
  for select using (
    assigned_officer_id = auth.uid()
    or exists (select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN'))
  );

create policy investigator_insert_cases on cases
  for insert with check (
    assigned_officer_id = auth.uid()
  );

-- Wallet Submissions: Access via case_id
create policy wallet_submissions_case_policy on wallet_submissions
  for select using (
    exists (
      select 1 from cases c
      where c.case_id = wallet_submissions.case_id
        and (c.assigned_officer_id = auth.uid() or exists (
          select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN')
        ))
    )
  );

-- Analysis Runs: Access via submission -> case
create policy analysis_runs_case_policy on analysis_runs
  for select using (
    exists (
      select 1 from wallet_submissions ws
      join cases c on c.case_id = ws.case_id
      where ws.submission_id = analysis_runs.submission_id
        and (c.assigned_officer_id = auth.uid() or exists (
          select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN')
        ))
    )
  );

-- Attributions: Access via analysis_run -> submission -> case
create policy attributions_case_policy on attributions
  for select using (
    exists (
      select 1 from analysis_runs ar
      join wallet_submissions ws on ws.submission_id = ar.submission_id
      join cases c on c.case_id = ws.case_id
      where ar.run_id = attributions.run_id
        and (c.assigned_officer_id = auth.uid() or exists (
          select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN')
        ))
    )
  );

-- Audit Log: Officer reads entries they generated; Supervisors & Admins read all
create policy audit_log_select_policy on audit_log
  for select using (
    officer_id = auth.uid()
    or exists (select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN'))
  );

create policy audit_log_insert_policy on audit_log
  for insert with check (
    officer_id = auth.uid()
  );

-- VASP Directory: All authenticated officers can read; only ADMIN can insert/update
create policy vasp_read_all on vasp_directory
  for select to authenticated using (true);

create policy vasp_admin_modify on vasp_directory
  for all using (
    exists (select 1 from profiles p where p.id = auth.uid() and p.role = 'ADMIN')
  );

-- Intel Tags: All authenticated officers can read and submit
create policy intel_tags_read on intel_tags
  for select to authenticated using (true);

create policy intel_tags_insert on intel_tags
  for insert to authenticated with check (submitted_by = auth.uid());

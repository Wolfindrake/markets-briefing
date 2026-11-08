-- Optional: a Supabase (Postgres) copy of the price history, for later features
-- (accounts, a richer journal, analytics). The site works without it.
-- Run this once in Supabase: SQL Editor -> New query -> paste -> Run.

create table if not exists public.prices (
  date     date        not null,
  key      text        not null,
  close    double precision,
  open     double precision,
  chg_pct  double precision,
  source   text,
  inserted_at timestamptz not null default now(),
  primary key (date, key)
);

create table if not exists public.journal (
  id           bigint generated always as identity primary key,
  session_date date not null,
  call         text check (call in ('Long', 'Short')),
  reason       text,
  conviction   text,
  created_at   timestamptz not null default now()
);

-- Row level security: nobody can read or write through the public (anon) key.
-- The pipeline uses the service-role key, which bypasses RLS.
alter table public.prices  enable row level security;
alter table public.journal enable row level security;

-- Supabase now requires explicit grants for API access on new projects.
grant usage on schema public to service_role;
grant select, insert, update, delete on public.prices  to service_role;
grant select, insert, update, delete on public.journal to service_role;

-- Optional read-only access for a future logged-in front end:
-- grant select on public.prices to authenticated;
-- create policy "read prices" on public.prices for select to authenticated using (true);

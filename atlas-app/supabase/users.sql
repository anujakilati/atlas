-- Run in Supabase SQL Editor if your users table / policies are not set up yet.
-- Expected columns: id (uuid), email (text), name (text), created_at (timestamptz)

create table if not exists public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  name text not null,
  created_at timestamptz not null default now()
);

alter table public.users enable row level security;

drop policy if exists "Users can read own profile" on public.users;
create policy "Users can read own profile"
  on public.users
  for select
  using (auth.uid() = id);

drop policy if exists "Users can insert own profile" on public.users;
create policy "Users can insert own profile"
  on public.users
  for insert
  with check (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.users;
create policy "Users can update own profile"
  on public.users
  for update
  using (auth.uid() = id);

-- Creates public.users when Supabase Auth creates auth.users (e.g. after email confirm)
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email, name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

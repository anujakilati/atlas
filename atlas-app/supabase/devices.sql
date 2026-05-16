-- Run in Supabase SQL Editor (safe to re-run).

create table if not exists public.devices (
  id uuid primary key default gen_random_uuid(),
  bubble uuid not null references public.bubbles (id) on delete cascade,
  name text not null,
  placement text not null default '',
  status text not null default 'pending',
  created_at timestamptz not null default now()
);

alter table public.devices add column if not exists placement text not null default '';
alter table public.devices add column if not exists contact text not null default '';
alter table public.devices add column if not exists device_token text;
alter table public.devices add column if not exists status text not null default 'pending';
alter table public.devices add column if not exists created_at timestamptz not null default now();

update public.devices set contact = '' where contact is null;
update public.devices set status = coalesce(status, 'pending');

-- Backfill tokens for existing rows (run once)
update public.devices
set device_token = upper(substring(replace(gen_random_uuid()::text, '-', '') from 1 for 8))
where device_token is null;

alter table public.devices alter column device_token set not null;

alter table public.devices drop constraint if exists devices_status_check;
alter table public.devices add constraint devices_status_check
  check (status in ('pending', 'online', 'offline'));

create unique index if not exists devices_device_token_idx on public.devices (device_token);
create index if not exists devices_bubble_idx on public.devices (bubble);

create table if not exists public.device_recordings (
  id uuid primary key default gen_random_uuid(),
  device uuid not null references public.devices (id) on delete cascade,
  storage_path text not null,
  duration_ms int,
  created_at timestamptz not null default now()
);

create index if not exists device_recordings_device_idx on public.device_recordings (device);

alter table public.devices enable row level security;
alter table public.device_recordings enable row level security;

grant select, insert, update, delete on table public.devices to authenticated;
grant select, insert on table public.device_recordings to authenticated, anon;

drop policy if exists "Members can view devices" on public.devices;
drop policy if exists "Members can insert devices" on public.devices;
drop policy if exists "Members can update devices" on public.devices;
drop policy if exists "Members can delete devices" on public.devices;

create policy "Members can view devices"
  on public.devices for select to authenticated
  using (
    exists (
      select 1 from public.bubbles b
      where b.id = bubble and auth.uid() = any (coalesce(b.members, '{}'::uuid[]))
    )
  );

create policy "Members can insert devices"
  on public.devices for insert to authenticated
  with check (
    exists (
      select 1 from public.bubbles b
      where b.id = bubble and auth.uid() = any (coalesce(b.members, '{}'::uuid[]))
    )
  );

create policy "Members can update devices"
  on public.devices for update to authenticated
  using (
    exists (
      select 1 from public.bubbles b
      where b.id = bubble and auth.uid() = any (coalesce(b.members, '{}'::uuid[]))
    )
  );

create policy "Members can delete devices"
  on public.devices for delete to authenticated
  using (
    exists (
      select 1 from public.bubbles b
      where b.id = bubble and auth.uid() = any (coalesce(b.members, '{}'::uuid[]))
    )
  );

drop policy if exists "Members can view recordings" on public.device_recordings;
drop policy if exists "Camera can insert recordings" on public.device_recordings;

create policy "Members can view recordings"
  on public.device_recordings for select to authenticated
  using (
    exists (
      select 1 from public.devices d
      join public.bubbles b on b.id = d.bubble
      where d.id = device and auth.uid() = any (coalesce(b.members, '{}'::uuid[]))
    )
  );

create policy "Camera can insert recordings"
  on public.device_recordings for insert to anon, authenticated
  with check (true);

-- Device app: register with token (no login)
create or replace function public.get_device_by_token(p_token text)
returns table (id uuid, name text, placement text, bubble_name text)
language sql
security definer
set search_path = public
as $$
  select d.id, d.name, d.placement, b.name as bubble_name
  from public.devices d
  join public.bubbles b on b.id = d.bubble
  where upper(trim(d.device_token)) = upper(trim(p_token));
$$;

grant execute on function public.get_device_by_token(text) to anon, authenticated;

create or replace function public.set_device_status_by_token(p_token text, p_status text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_status not in ('pending', 'online', 'offline') then
    raise exception 'Invalid status';
  end if;
  update public.devices
  set status = p_status
  where upper(trim(device_token)) = upper(trim(p_token));
end;
$$;

grant execute on function public.set_device_status_by_token(text, text) to anon, authenticated;

-- Legacy helpers (optional)
create or replace function public.set_device_status(p_device_id uuid, p_status text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_status not in ('pending', 'online', 'offline') then
    raise exception 'Invalid status';
  end if;
  update public.devices set status = p_status where id = p_device_id;
end;
$$;

grant execute on function public.set_device_status(uuid, text) to anon, authenticated;

insert into storage.buckets (id, name, public)
values ('camera-feeds', 'camera-feeds', true)
on conflict (id) do update set public = true;

drop policy if exists "Public read camera feeds" on storage.objects;
drop policy if exists "Upload camera feeds" on storage.objects;
drop policy if exists "Update camera feeds" on storage.objects;

create policy "Public read camera feeds"
  on storage.objects for select to anon, authenticated
  using (bucket_id = 'camera-feeds');

create policy "Upload camera feeds"
  on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'camera-feeds');

create policy "Update camera feeds"
  on storage.objects for update to anon, authenticated
  using (bucket_id = 'camera-feeds')
  with check (bucket_id = 'camera-feeds');

notify pgrst, 'reload schema';

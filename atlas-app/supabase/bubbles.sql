-- Run this entire file in Supabase SQL Editor.
-- Fixes 403 on create: you need SELECT + INSERT policies (insert with .select() requires both).

alter table public.bubbles
  alter column devices set default '{}'::uuid[];

alter table public.bubbles
  alter column members set default '{}'::uuid[];

alter table public.bubbles
  add column if not exists invite_token text unique;

create unique index if not exists bubbles_invite_token_idx on public.bubbles (invite_token);

alter table public.bubbles enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update on table public.bubbles to authenticated;

-- Remove old / incomplete policies (including custom add_bubble, update_bubble)
drop policy if exists "add_bubble" on public.bubbles;
drop policy if exists "update_bubble" on public.bubbles;
drop policy if exists "Members can view bubbles" on public.bubbles;
drop policy if exists "Users can create bubbles" on public.bubbles;
drop policy if exists "Members can update bubbles" on public.bubbles;

-- SELECT (required for .insert().select() and dashboard)
create policy "Members can view bubbles"
  on public.bubbles for select
  to authenticated
  using (auth.uid() = any (members));

-- INSERT (creator must be in members array — app sends members: [user.id])
create policy "Users can create bubbles"
  on public.bubbles for insert
  to authenticated
  with check (auth.uid() = any (members));

-- UPDATE (join adds user to members)
create policy "Members can update bubbles"
  on public.bubbles for update
  to authenticated
  using (auth.uid() = any (members));

create or replace function public.join_bubble_by_id(p_bubble_id uuid)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Not authenticated';
  end if;

  if not exists (select 1 from public.bubbles where id = p_bubble_id) then
    raise exception 'Bubble not found';
  end if;

  update public.bubbles
  set members = coalesce(members, '{}'::uuid[]) || array[auth.uid()]
  where id = p_bubble_id
    and not (auth.uid() = any (coalesce(members, '{}'::uuid[])));

  update public.users
  set bubbles = coalesce(bubbles, '{}'::uuid[]) || array[p_bubble_id]
  where id = auth.uid()
    and not (p_bubble_id = any (coalesce(bubbles, '{}'::uuid[])));

  return p_bubble_id;
end;
$$;

grant execute on function public.join_bubble_by_id(uuid) to authenticated;

create or replace function public.join_bubble_by_token(p_token text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_bubble_id uuid;
begin
  if auth.uid() is null then
    raise exception 'Not authenticated';
  end if;

  select id into v_bubble_id
  from public.bubbles
  where upper(invite_token) = upper(trim(p_token));

  if v_bubble_id is null then
    raise exception 'Invalid invite code';
  end if;

  update public.bubbles
  set members = coalesce(members, '{}'::uuid[]) || array[auth.uid()]
  where id = v_bubble_id
    and not (auth.uid() = any (coalesce(members, '{}'::uuid[])));

  update public.users
  set bubbles = coalesce(bubbles, '{}'::uuid[]) || array[v_bubble_id]
  where id = auth.uid()
    and not (v_bubble_id = any (coalesce(bubbles, '{}'::uuid[])));

  return v_bubble_id;
end;
$$;

grant execute on function public.join_bubble_by_token(text) to authenticated;

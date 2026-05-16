-- Matches your users table: id, username, bubbles (uuid[])

alter table public.users
  alter column bubbles set default '{}'::uuid[];

alter table public.users enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update on table public.users to authenticated;

drop policy if exists "Users can read own profile" on public.users;
create policy "Users can read own profile"
  on public.users for select
  using (auth.uid() = id);

drop policy if exists "Users can insert own profile" on public.users;
create policy "Users can insert own profile"
  on public.users for insert
  with check (auth.uid() = id);

drop policy if exists "Users can update own profile" on public.users;
create policy "Users can update own profile"
  on public.users for update
  using (auth.uid() = id);

-- Append a bubble id to the logged-in user's bubbles uuid[] (create / join)
create or replace function public.add_bubble_to_user(p_bubble_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then
    raise exception 'Not authenticated';
  end if;

  update public.users
  set bubbles = coalesce(bubbles, '{}'::uuid[]) || array[p_bubble_id]
  where id = auth.uid()
    and not (p_bubble_id = any (coalesce(bubbles, '{}'::uuid[])));
end;
$$;

grant execute on function public.add_bubble_to_user(uuid) to authenticated;

-- Creates public.users row when Supabase Auth creates auth.users
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, username, bubbles)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1)),
    '{}'::uuid[]
  )
  on conflict (id) do update set
    username = excluded.username;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

-- Backfill existing auth users into public.users
insert into public.users (id, username, bubbles)
select
  u.id,
  coalesce(u.raw_user_meta_data ->> 'name', split_part(u.email, '@', 1)),
  '{}'::uuid[]
from auth.users u
where not exists (select 1 from public.users p where p.id = u.id)
on conflict (id) do nothing;

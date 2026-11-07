-- =====================================================================
-- Ecotroca — 02: perfis (profiles) ligados ao Supabase Auth
-- Idempotente: pode ser executado mais de uma vez.
-- Depende de: nada além do Supabase Auth.
-- =====================================================================

create table if not exists public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  apelido      text not null,
  cidade       text not null default 'Sorocaba',
  pontos_total integer not null default 0,
  criado_em    timestamptz not null default now(),

  constraint profiles_apelido_formato  check (apelido ~ '^[A-Za-z0-9_]{3,20}$'),
  constraint profiles_cidade_valida    check (length(btrim(cidade)) between 1 and 60),
  constraint profiles_pontos_positivos check (pontos_total >= 0)
);

comment on table  public.profiles is 'Perfil público-do-app de cada usuário (1 linha por auth.users). Criado pelo trigger handle_new_user.';
comment on column public.profiles.apelido      is 'Único sem diferenciar maiúsculas; 3 a 20 caracteres: letras, números e _.';
comment on column public.profiles.pontos_total is 'Só é alterado por registrar_descarte(). O usuário nunca escreve nesta coluna.';

-- Apelido único sem diferenciar maiúsculas de minúsculas ("Ana" e "ana" são o mesmo apelido)
create unique index if not exists profiles_apelido_unico on public.profiles (lower(apelido));

-- ---------------------------------------------------------------------
-- Trigger: cada novo usuário do Auth ganha uma linha em profiles.
-- O apelido vem de raw_user_meta_data ("data" do signUp). Se for inválido
-- ou já existir, o cadastro inteiro é recusado.
-- ---------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_apelido text := coalesce(new.raw_user_meta_data ->> 'apelido', '');
begin
  if v_apelido !~ '^[A-Za-z0-9_]{3,20}$' then
    raise exception 'Apelido inválido: use de 3 a 20 letras, números ou _.'
      using errcode = 'check_violation';
  end if;

  insert into public.profiles (id, apelido) values (new.id, v_apelido);
  return new;
end;
$$;

-- Função de trigger: ninguém a chama por RPC.
revoke all on function public.handle_new_user() from public, anon, authenticated;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- Segurança: RLS + privilégios mínimos
--  - anônimo: nada
--  - logado: lê só o próprio perfil e altera só apelido e cidade
--  - insert (trigger) e pontos_total (registrar_descarte) só por funções do banco
-- ---------------------------------------------------------------------
alter table public.profiles enable row level security;

revoke all on table public.profiles from anon, authenticated;
grant select on table public.profiles to authenticated;
grant update (apelido, cidade) on table public.profiles to authenticated;

drop policy if exists "profiles_le_o_proprio" on public.profiles;
create policy "profiles_le_o_proprio"
  on public.profiles
  for select
  to authenticated
  using (id = (select auth.uid()));

drop policy if exists "profiles_altera_o_proprio" on public.profiles;
create policy "profiles_altera_o_proprio"
  on public.profiles
  for update
  to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

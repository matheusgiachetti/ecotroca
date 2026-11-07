-- =====================================================================
-- Ecotroca — 07: medalhas e regras públicas
--   medalhas, usuario_medalhas   → catálogo e conquistas
--   conceder_medalhas(uuid)      → interna: chamada por registrar_descarte (05), nunca pelo cliente
--   minhas_medalhas()            → todas as medalhas, com conquistada true/false (só logado)
--   regras_pontos()              → regras para a página (pública): tipos, limites, níveis, medalhas
-- Idempotente. Depende de 02 a 05. Aplique DEPOIS da 05 (ou junto, na ordem 05 → 07).
--
-- Medalha NÃO dá pontos: pontos_total só muda em registrar_descarte, pelo valor do descarte.
-- Quem concede é o banco, dentro de registrar_descarte, depois de gravar o descarte.
-- Os NÚMEROS das regras (raio, limites, níveis) ficam em regras_limites() (05); os limiares das
-- medalhas (10 itens, 3 tipos, 100 pontos) ficam em conceder_medalhas() e nas descrições abaixo.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Catálogo (leitura só para quem está logado; a página pública lê por regras_pontos())
-- ---------------------------------------------------------------------
create table if not exists public.medalhas (
  codigo    text primary key,
  nome      text not null,
  descricao text not null,
  ordem     smallint not null default 0,

  constraint medalhas_codigo_valido check (codigo ~ '^[a-z0-9_]{2,40}$'),
  constraint medalhas_nome_preenchido check (length(btrim(nome)) > 0)
);

comment on table public.medalhas is 'Catálogo de medalhas. As condições vivem em conceder_medalhas(); medalha não dá pontos.';

insert into public.medalhas (codigo, nome, descricao, ordem) values
  ('primeiro_descarte', 'Primeiro descarte',       'Registrou o primeiro descarte.',               1),
  ('dez_itens',         '10 itens descartados',    'Descartou 10 itens, somando todos os registros.', 2),
  ('tres_tipos',        '3 tipos de resíduo',      'Descartou 3 tipos diferentes de resíduo.',      3),
  ('cem_pontos',        '100 pontos',              'Chegou a 100 pontos.',                          4)
on conflict (codigo) do update
  set nome = excluded.nome, descricao = excluded.descricao, ordem = excluded.ordem;

-- ---------------------------------------------------------------------
-- Conquistas: o usuário lê só as próprias; ninguém escreve direto
-- ---------------------------------------------------------------------
create table if not exists public.usuario_medalhas (
  user_id        uuid not null references public.profiles (id) on delete cascade,
  medalha_codigo text not null references public.medalhas (codigo) on delete cascade,
  conquistada_em timestamptz not null default now(),
  primary key (user_id, medalha_codigo)
);

comment on table public.usuario_medalhas is 'Medalhas conquistadas. Só conceder_medalhas() grava.';

alter table public.medalhas enable row level security;
alter table public.usuario_medalhas enable row level security;

revoke all on table public.medalhas from anon, authenticated;
revoke all on table public.usuario_medalhas from anon, authenticated;
grant select on table public.medalhas to authenticated;
grant select on table public.usuario_medalhas to authenticated;

drop policy if exists "medalhas_leitura_logado" on public.medalhas;
create policy "medalhas_leitura_logado"
  on public.medalhas
  for select
  to authenticated
  using (true);

drop policy if exists "usuario_medalhas_le_as_proprias" on public.usuario_medalhas;
create policy "usuario_medalhas_le_as_proprias"
  on public.usuario_medalhas
  for select
  to authenticated
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------
-- conceder_medalhas: INTERNA. Confere as condições NO BANCO e insere o que faltar
-- ("on conflict do nothing": nunca concede duas vezes). Devolve os NOMES das medalhas
-- conquistadas nesta chamada, em jsonb. Ninguém a chama por RPC.
-- ---------------------------------------------------------------------
create or replace function public.conceder_medalhas(p_uid uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  c_itens_para_medalha  constant integer := 10;
  c_tipos_para_medalha  constant integer := 3;
  c_pontos_para_medalha constant integer := 100;

  v_descartes integer;
  v_itens     integer;
  v_tipos     integer;
  v_pontos    integer;
  v_novas     jsonb;
begin
  select count(*), coalesce(sum(quantidade), 0), count(distinct tipo_id)
    into v_descartes, v_itens, v_tipos
    from public.descartes
   where user_id = p_uid;
  select pontos_total into v_pontos from public.profiles where id = p_uid;

  with ganhas as (
    insert into public.usuario_medalhas (user_id, medalha_codigo)
    select p_uid, m.codigo
      from public.medalhas m
     where (m.codigo = 'primeiro_descarte' and v_descartes >= 1)
        or (m.codigo = 'dez_itens'         and v_itens  >= c_itens_para_medalha)
        or (m.codigo = 'tres_tipos'        and v_tipos  >= c_tipos_para_medalha)
        or (m.codigo = 'cem_pontos'        and coalesce(v_pontos, 0) >= c_pontos_para_medalha)
    on conflict do nothing
    returning medalha_codigo
  )
  select coalesce(jsonb_agg(m.nome order by m.ordem), '[]'::jsonb)
    into v_novas
    from ganhas g
    join public.medalhas m on m.codigo = g.medalha_codigo;

  return v_novas;
end;
$$;

revoke all on function public.conceder_medalhas(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------
-- minhas_medalhas — SECURITY INVOKER: a RLS do usuário já limita às conquistas dele.
-- ---------------------------------------------------------------------
create or replace function public.minhas_medalhas()
returns table (codigo text, nome text, descricao text, conquistada boolean, conquistada_em timestamptz)
language plpgsql
stable
set search_path = ''
as $$
begin
  if auth.uid() is null then
    raise exception 'Entre na sua conta para ver as suas medalhas.' using hint = 'nao_logado';
  end if;

  return query
  select m.codigo, m.nome, m.descricao, um.medalha_codigo is not null, um.conquistada_em
    from public.medalhas m
    left join public.usuario_medalhas um
           on um.medalha_codigo = m.codigo and um.user_id = auth.uid()
   order by m.ordem, m.codigo;
end;
$$;

revoke all on function public.minhas_medalhas() from public, anon, authenticated;
grant execute on function public.minhas_medalhas() to authenticated;

-- ---------------------------------------------------------------------
-- regras_pontos — PÚBLICA. Tudo o que a página "Como os pontos funcionam" mostra, lido do banco:
-- o site nunca repete esses números. Sem dados de ninguém: só regras.
-- ---------------------------------------------------------------------
create or replace function public.regras_pontos()
returns jsonb
language sql
security definer
stable
set search_path = ''
as $$
  select jsonb_build_object(
    'tipos', (select coalesce(jsonb_agg(jsonb_build_object('nome', t.nome, 'pontos', t.pontos) order by t.id), '[]'::jsonb)
                from public.tipos_residuo t),
    'raio_m',         (public.regras_limites() ->> 'raio_m')::integer,
    'max_registros',  (public.regras_limites() ->> 'max_registros')::integer,
    'max_itens',      (public.regras_limites() ->> 'max_itens')::integer,
    'quantidade_max', (public.regras_limites() ->> 'quantidade_max')::integer,
    'fuso',           public.regras_limites() ->> 'fuso',
    'niveis',         public.regras_limites() -> 'niveis',
    'medalhas', (select coalesce(jsonb_agg(jsonb_build_object('nome', m.nome, 'descricao', m.descricao) order by m.ordem, m.codigo), '[]'::jsonb)
                   from public.medalhas m)
  );
$$;

revoke all on function public.regras_pontos() from public, anon, authenticated;
grant execute on function public.regras_pontos() to anon, authenticated;

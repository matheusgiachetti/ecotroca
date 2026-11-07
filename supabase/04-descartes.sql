-- =====================================================================
-- Ecotroca — 04: descartes registrados pelos usuários
-- Ninguém escreve aqui direto: só a função registrar_descarte() (05).
-- Idempotente.
-- =====================================================================

create table if not exists public.descartes (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references public.profiles (id) on delete cascade,
  -- Se um ponto for apagado, o histórico do usuário permanece (ponto_id fica nulo).
  ponto_id          uuid references public.pontos_coleta (id) on delete set null,
  tipo_id           smallint not null references public.tipos_residuo (id) on delete restrict,
  quantidade        smallint not null,
  pontos            integer not null,
  peso_kg_estimado  numeric(8, 3) not null,
  criado_em         timestamptz not null default now(),

  constraint descartes_quantidade_valida check (quantidade between 1 and 10),
  constraint descartes_pontos_positivos  check (pontos > 0),
  constraint descartes_peso_positivo     check (peso_kg_estimado > 0)
);

comment on table  public.descartes is 'Um registro por descarte confirmado por proximidade. Não guarda a posição do usuário.';
comment on column public.descartes.pontos is 'Calculado no banco: tipos_residuo.pontos × quantidade.';

-- Índices: histórico por usuário/dia (limites diários e meu_resumo) e chaves estrangeiras
create index if not exists descartes_user_criado_idx on public.descartes (user_id, criado_em desc);
create index if not exists descartes_ponto_idx       on public.descartes (ponto_id);
create index if not exists descartes_tipo_idx        on public.descartes (tipo_id);

-- Segurança: o usuário só LÊ os próprios descartes. Sem INSERT/UPDATE/DELETE.
alter table public.descartes enable row level security;

revoke all on table public.descartes from anon, authenticated;
grant select on table public.descartes to authenticated;

drop policy if exists "descartes_le_os_proprios" on public.descartes;
create policy "descartes_le_os_proprios"
  on public.descartes
  for select
  to authenticated
  using (user_id = (select auth.uid()));

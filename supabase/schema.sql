-- =====================================================================
-- Ecotroca — esquema do banco (Supabase / Postgres)
-- Tabela de pontos de coleta de lixo eletrônico (REEE).
-- Pode ser executado mais de uma vez sem erro (idempotente).
-- =====================================================================

create table if not exists public.pontos_coleta (
  id               uuid primary key default gen_random_uuid(),
  nome             text not null,
  endereco         text not null,
  latitude         double precision not null,
  longitude        double precision not null,
  horario          text,
  residuos_aceitos text[] not null default '{}',
  telefone         text,
  fonte            text,
  verificado       boolean not null default false,
  criado_em        timestamptz not null default now(),

  -- Validações básicas para evitar dados inválidos
  constraint pontos_coleta_nome_preenchido     check (length(btrim(nome)) > 0),
  constraint pontos_coleta_endereco_preenchido check (length(btrim(endereco)) > 0),
  constraint pontos_coleta_latitude_valida     check (latitude  between -90  and 90),
  constraint pontos_coleta_longitude_valida    check (longitude between -180 and 180)
);

comment on table  public.pontos_coleta is 'Pontos de coleta de lixo eletrônico exibidos no mapa da Ecotroca.';
comment on column public.pontos_coleta.fonte      is 'De onde veio a informação (ex.: SINIR, prefeitura, contato com o responsável).';
comment on column public.pontos_coleta.verificado is 'true somente depois de conferir os dados com a fonte oficial ou o responsável.';

-- ---------------------------------------------------------------------
-- Segurança: leitura pública, nenhuma escrita pelo navegador.
-- As alterações devem ser feitas pelo painel do Supabase (SQL Editor /
-- Table Editor), que usa um papel com privilégios de administrador.
-- ---------------------------------------------------------------------
alter table public.pontos_coleta enable row level security;

-- Privilégios mínimos: os papéis públicos só podem ler.
revoke all on table public.pontos_coleta from anon, authenticated;
grant select on table public.pontos_coleta to anon, authenticated;

drop policy if exists "pontos_coleta_leitura_publica" on public.pontos_coleta;
create policy "pontos_coleta_leitura_publica"
  on public.pontos_coleta
  for select
  to anon, authenticated
  using (true);

-- Não existem políticas de INSERT/UPDATE/DELETE: com RLS ativo,
-- qualquer tentativa de escrita com a chave pública é bloqueada.

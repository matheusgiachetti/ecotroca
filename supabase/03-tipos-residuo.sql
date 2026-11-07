-- =====================================================================
-- Ecotroca — 03: tipos de resíduo (pontos e peso por item)
-- Os nomes são EXATAMENTE os das categorias dos filtros do site (js/main.js).
-- Idempotente: reexecutar atualiza pontos, peso e fonte pelo nome.
-- =====================================================================

create table if not exists public.tipos_residuo (
  id               smallint generated always as identity primary key,
  nome             text not null,
  pontos           integer not null,
  peso_estimado_kg numeric(6, 3) not null,
  fonte            text not null,

  constraint tipos_residuo_nome_unico      unique (nome),
  constraint tipos_residuo_nome_preenchido check (length(btrim(nome)) > 0),
  constraint tipos_residuo_pontos_positivos check (pontos > 0),
  constraint tipos_residuo_peso_positivo   check (peso_estimado_kg > 0)
);

comment on table  public.tipos_residuo is 'Quanto vale (pontos) e quanto pesa (kg estimado) cada ITEM descartado de cada categoria.';
comment on column public.tipos_residuo.peso_estimado_kg is 'Peso médio estimado de UM item. Estimativa, não medição.';
comment on column public.tipos_residuo.fonte is 'De onde vem o peso. Só referência verificável; senão "estimativa do grupo - revisar".';

-- Os pesos abaixo são estimativas do grupo para um item médio e AINDA NÃO têm fonte verificada.
insert into public.tipos_residuo (nome, pontos, peso_estimado_kg, fonte) values
  ('Pilhas e baterias',          5,  0.025, 'estimativa do grupo - revisar'),
  ('Cabos e carregadores',       5,  0.150, 'estimativa do grupo - revisar'),
  ('Celulares',                  20, 0.170, 'estimativa do grupo - revisar'),
  ('Computadores e periféricos', 50, 2.000, 'estimativa do grupo - revisar'),
  ('Eletrodomésticos pequenos',  30, 1.200, 'estimativa do grupo - revisar')
on conflict (nome) do update
  set pontos           = excluded.pontos,
      peso_estimado_kg = excluded.peso_estimado_kg,
      fonte            = excluded.fonte;

-- Leitura pública; escrita só pelo painel do Supabase.
alter table public.tipos_residuo enable row level security;

revoke all on table public.tipos_residuo from anon, authenticated;
grant select on table public.tipos_residuo to anon, authenticated;

drop policy if exists "tipos_residuo_leitura_publica" on public.tipos_residuo;
create policy "tipos_residuo_leitura_publica"
  on public.tipos_residuo
  for select
  to anon, authenticated
  using (true);

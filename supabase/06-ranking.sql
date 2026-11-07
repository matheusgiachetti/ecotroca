-- =====================================================================
-- Ecotroca — 06: ranking
--   ranking(periodo, cidade, limite)   → top de quem pontuou (leitura PÚBLICA)
--   minha_posicao(periodo, cidade)     → a posição de quem está logado
--   ranking_linhas(periodo, cidade)    → auxiliar interna (ninguém a chama por RPC)
-- Idempotente. Depende de 02 e 04.
--
-- PRIVACIDADE: o ranking público mostra SÓ apelido, cidade, pontos do período e
-- posição. Nunca id, e-mail nem dados de descarte (ponto, tipo, hora, peso).
-- As funções são SECURITY DEFINER para somar descartes de todo mundo sem abrir
-- as tabelas: anon e authenticated continuam sem ler profiles nem descartes.
--
-- Períodos (fuso de Brasília, como em registrar_descarte):
--   'semana' = da segunda-feira 00:00 até agora · 'mes' = do dia 1º 00:00 até agora · 'geral' = tudo
-- Erros de regra levantam exceção com HINT estável: periodo_invalido · nao_logado
-- =====================================================================

-- Índice para os filtros por período (semana e mês varrem por data)
create index if not exists descartes_criado_idx on public.descartes (criado_em);

-- ---------------------------------------------------------------------
-- ranking_linhas: TODAS as pessoas que pontuaram no período, já com a posição.
-- Ordem: pontos do período (maior primeiro), depois o apelido (empate estável).
-- Cidade nula ou em branco = todas; senão compara sem diferenciar maiúsculas.
-- Quem não pontuou no período não aparece (o join parte de descartes).
-- ---------------------------------------------------------------------
create or replace function public.ranking_linhas(p_periodo text, p_cidade text)
returns table (user_id uuid, posicao integer, apelido text, cidade text, pontos integer)
language plpgsql
stable
set search_path = ''
as $$
declare
  c_tz     constant text := 'America/Sao_Paulo';
  v_inicio timestamptz;
  v_cidade text := nullif(btrim(p_cidade), '');
begin
  v_inicio := case p_periodo
    when 'semana' then date_trunc('week',  now() at time zone c_tz) at time zone c_tz  -- semana começa na segunda
    when 'mes'    then date_trunc('month', now() at time zone c_tz) at time zone c_tz
    when 'geral'  then '-infinity'::timestamptz
    else null
  end;
  if v_inicio is null then
    raise exception 'Período inválido: use semana, mes ou geral.' using hint = 'periodo_invalido';
  end if;

  return query
  select t.user_id,
         (row_number() over (order by t.soma desc, lower(t.apelido), t.apelido))::integer,
         t.apelido,
         t.cidade,
         t.soma
    from (
      select pr.id as user_id, pr.apelido, pr.cidade, sum(d.pontos)::integer as soma
        from public.descartes d
        join public.profiles pr on pr.id = d.user_id
       where d.criado_em >= v_inicio
         and (v_cidade is null or lower(btrim(pr.cidade)) = lower(v_cidade))
       group by pr.id, pr.apelido, pr.cidade
    ) t;
end;
$$;

revoke all on function public.ranking_linhas(text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------------
-- ranking: leitura pública. Só posicao, apelido, cidade e pontos.
-- Limite: no máximo 50; nulo, zero ou negativo vira o padrão de 10.
-- ---------------------------------------------------------------------
create or replace function public.ranking(
  p_periodo text    default 'geral',
  p_cidade  text    default null,
  p_limite  integer default 10
)
returns table (posicao integer, apelido text, cidade text, pontos integer)
language plpgsql
security definer
stable
set search_path = ''
as $$
declare
  v_limite integer := case when p_limite is null or p_limite < 1 then 10 else least(p_limite, 50) end;
begin
  return query
  select l.posicao, l.apelido, l.cidade, l.pontos
    from public.ranking_linhas(p_periodo, p_cidade) l
   order by l.posicao
   limit v_limite;
end;
$$;

revoke all on function public.ranking(text, text, integer) from public, anon, authenticated;
-- Quem está logado também usa o papel "authenticated" e precisa ver o ranking.
grant execute on function public.ranking(text, text, integer) to anon, authenticated;

-- ---------------------------------------------------------------------
-- minha_posicao: só para quem está logado. A posição e os pontos da própria pessoa
-- no período (e no filtro de cidade). Nenhuma linha se ela não pontuou.
-- ---------------------------------------------------------------------
create or replace function public.minha_posicao(p_periodo text default 'geral', p_cidade text default null)
returns table (posicao integer, pontos integer)
language plpgsql
security definer
stable
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'Entre na sua conta para ver a sua posição.' using hint = 'nao_logado';
  end if;

  return query
  select l.posicao, l.pontos
    from public.ranking_linhas(p_periodo, p_cidade) l
   where l.user_id = v_uid;
end;
$$;

revoke all on function public.minha_posicao(text, text) from public, anon, authenticated;
grant execute on function public.minha_posicao(text, text) to authenticated;

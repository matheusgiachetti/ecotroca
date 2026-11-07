-- =====================================================================
-- Ecotroca — 05: funções do sistema de pontos
--   nivel_por_pontos(int)  → nome do nível
--   registrar_descarte(...) → único jeito de ganhar pontos (SECURITY DEFINER)
--   meu_resumo()            → pontos, nível, descartes e kg do usuário (invoker)
-- Idempotente. Depende de 02, 03 e 04.
--
-- Erros de regra levantam exceção com HINT estável, para o site traduzir:
--   nao_logado · quantidade_invalida · coordenadas_invalidas · ponto_inexistente
--   tipo_inexistente · perfil_inexistente · longe_do_ponto · limite_registros · limite_itens
-- =====================================================================

-- Nível pelo total de pontos: Semente 0–49, Broto 50–149, Muda 150–349, Árvore 350–699, Floresta 700+
create or replace function public.nivel_por_pontos(p_pontos integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_pontos >= 700 then 'Floresta'
    when p_pontos >= 350 then 'Árvore'
    when p_pontos >= 150 then 'Muda'
    when p_pontos >= 50  then 'Broto'
    else 'Semente'
  end;
$$;

revoke all on function public.nivel_por_pontos(integer) from public, anon, authenticated;
grant execute on function public.nivel_por_pontos(integer) to authenticated;

-- ---------------------------------------------------------------------
-- registrar_descarte
-- Regras (todas no banco, nada vem do cliente além do que o usuário informou):
--  1. exige usuário logado
--  2. quantidade de 1 a 10
--  3. o usuário precisa estar a no máximo 200 m do ponto (Haversine, com as
--     coordenadas do ponto guardadas no banco)
--  4. no máximo 5 registros e 30 itens por dia (dia de Brasília) por usuário
--  5. pontos e peso saem de tipos_residuo × quantidade
-- A latitude/longitude do usuário é usada só para a conta e NÃO é gravada.
-- ---------------------------------------------------------------------
create or replace function public.registrar_descarte(
  p_ponto_id   uuid,
  p_tipo_id    integer,
  p_quantidade integer,
  p_lat        double precision,
  p_lng        double precision
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  c_raio_max_m   constant double precision := 200;
  c_max_registros constant integer := 5;
  c_max_itens     constant integer := 30;
  c_tz            constant text := 'America/Sao_Paulo';

  v_uid       uuid := auth.uid();
  v_ponto     record;
  v_tipo      record;
  v_dist_m    double precision;
  v_inicio    timestamptz;
  v_registros integer;
  v_itens     integer;
  v_pontos    integer;
  v_peso      numeric;
  v_total     integer;
  v_id        uuid;
begin
  if v_uid is null then
    raise exception 'Entre na sua conta para registrar um descarte.' using hint = 'nao_logado';
  end if;

  if p_quantidade is null or p_quantidade < 1 or p_quantidade > 10 then
    raise exception 'A quantidade deve ser de 1 a 10 itens.' using hint = 'quantidade_invalida';
  end if;

  if p_lat is null or p_lng is null
     or not (p_lat between -90 and 90) or not (p_lng between -180 and 180) then
    raise exception 'Não foi possível ler a sua localização.' using hint = 'coordenadas_invalidas';
  end if;

  select id, latitude, longitude into v_ponto from public.pontos_coleta where id = p_ponto_id;
  if not found then
    raise exception 'Ponto de coleta não encontrado.' using hint = 'ponto_inexistente';
  end if;

  select id, pontos, peso_estimado_kg into v_tipo from public.tipos_residuo where id = p_tipo_id;
  if not found then
    raise exception 'Tipo de resíduo não encontrado.' using hint = 'tipo_inexistente';
  end if;

  -- Distância em metros (Haversine, raio médio da Terra 6.371 km)
  v_dist_m := 2 * 6371000 * asin(least(1, sqrt(
      sin(radians(p_lat - v_ponto.latitude) / 2) ^ 2
    + cos(radians(v_ponto.latitude)) * cos(radians(p_lat))
      * sin(radians(p_lng - v_ponto.longitude) / 2) ^ 2
  )));
  if v_dist_m > c_raio_max_m then
    raise exception 'Você precisa estar a até 200 m do ponto de coleta para registrar o descarte.'
      using hint = 'longe_do_ponto';
  end if;

  -- Trava a linha do perfil: duas chamadas ao mesmo tempo não furam o limite diário.
  perform 1 from public.profiles where id = v_uid for update;
  if not found then
    raise exception 'Perfil não encontrado.' using hint = 'perfil_inexistente';
  end if;

  v_inicio := date_trunc('day', now() at time zone c_tz) at time zone c_tz;
  select count(*), coalesce(sum(quantidade), 0)
    into v_registros, v_itens
    from public.descartes
   where user_id = v_uid and criado_em >= v_inicio;

  if v_registros >= c_max_registros then
    raise exception 'Você já fez 5 registros hoje. Volte amanhã.' using hint = 'limite_registros';
  end if;
  if v_itens + p_quantidade > c_max_itens then
    raise exception 'O limite é de 30 itens por dia. Você ainda pode registrar % hoje.', c_max_itens - v_itens
      using hint = 'limite_itens';
  end if;

  v_pontos := v_tipo.pontos * p_quantidade;
  v_peso   := v_tipo.peso_estimado_kg * p_quantidade;

  insert into public.descartes (user_id, ponto_id, tipo_id, quantidade, pontos, peso_kg_estimado)
  values (v_uid, v_ponto.id, v_tipo.id, p_quantidade, v_pontos, v_peso)
  returning id into v_id;

  update public.profiles
     set pontos_total = pontos_total + v_pontos
   where id = v_uid
   returning pontos_total into v_total;

  return jsonb_build_object(
    'descarte_id',      v_id,
    'pontos_ganhos',    v_pontos,
    'pontos_total',     v_total,
    'nivel',            public.nivel_por_pontos(v_total),
    'peso_kg_estimado', v_peso
  );
end;
$$;

revoke all on function public.registrar_descarte(uuid, integer, integer, double precision, double precision)
  from public, anon, authenticated;
grant execute on function public.registrar_descarte(uuid, integer, integer, double precision, double precision)
  to authenticated;

-- ---------------------------------------------------------------------
-- meu_resumo — SECURITY INVOKER: lê com as permissões (e a RLS) do próprio usuário.
-- ---------------------------------------------------------------------
create or replace function public.meu_resumo()
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  v_uid       uuid := auth.uid();
  v_total     integer;
  v_registros integer;
  v_itens     integer;
  v_kg        numeric;
begin
  if v_uid is null then
    raise exception 'Entre na sua conta para ver o seu resumo.' using hint = 'nao_logado';
  end if;

  select pontos_total into v_total from public.profiles where id = v_uid;
  if not found then
    raise exception 'Perfil não encontrado.' using hint = 'perfil_inexistente';
  end if;

  select count(*), coalesce(sum(quantidade), 0), coalesce(sum(peso_kg_estimado), 0)
    into v_registros, v_itens, v_kg
    from public.descartes
   where user_id = v_uid;

  return jsonb_build_object(
    'pontos_total',  v_total,
    'nivel',         public.nivel_por_pontos(v_total),
    'descartes',     v_registros,
    'itens',         v_itens,
    'kg_estimados',  v_kg
  );
end;
$$;

revoke all on function public.meu_resumo() from public, anon, authenticated;
grant execute on function public.meu_resumo() to authenticated;

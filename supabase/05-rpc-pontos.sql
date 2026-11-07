-- =====================================================================
-- Ecotroca — 05: funções do sistema de pontos
--   regras_limites()        → ÚNICA fonte dos números das regras (raio, limites diários, níveis)
--   nivel_por_pontos(int)  → nome do nível (lido de regras_limites)
--   registrar_descarte(...) → único jeito de ganhar pontos (SECURITY DEFINER)
--   meu_resumo()            → pontos, nível, descartes e kg do usuário (invoker)
-- Idempotente. Depende de 02, 03 e 04. As medalhas (07) são opcionais aqui: se
-- conceder_medalhas() ainda não existir, registrar_descarte() só não concede nada.
--
-- Erros de regra levantam exceção com HINT estável, para o site traduzir:
--   nao_logado · quantidade_invalida · coordenadas_invalidas · ponto_inexistente
--   tipo_inexistente · perfil_inexistente · longe_do_ponto · limite_registros · limite_itens
-- =====================================================================

-- ---------------------------------------------------------------------
-- regras_limites: ÚNICA fonte dos números das regras. Para mudar um limite ou um
-- nível, mude SÓ aqui: registrar_descarte, nivel_por_pontos e regras_pontos (07),
-- que alimenta o site, leem daqui.
--   raio_m 200 · max_registros 5 e max_itens 30 por dia (no fuso abaixo) · quantidade_max 10 por registro
--   níveis: Semente 0–49, Broto 50–149, Muda 150–349, Árvore 350–699, Floresta 700+
-- ---------------------------------------------------------------------
create or replace function public.regras_limites()
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select '{
    "raio_m": 200,
    "max_registros": 5,
    "max_itens": 30,
    "quantidade_max": 10,
    "fuso": "America/Sao_Paulo",
    "niveis": [
      {"nome": "Semente",  "de": 0},
      {"nome": "Broto",    "de": 50},
      {"nome": "Muda",     "de": 150},
      {"nome": "Árvore",   "de": 350},
      {"nome": "Floresta", "de": 700}
    ]
  }'::jsonb;
$$;

revoke all on function public.regras_limites() from public, anon, authenticated;
grant execute on function public.regras_limites() to authenticated;  -- meu_resumo (invoker) chama nivel_por_pontos

-- Nível pelo total de pontos (lido de regras_limites)
create or replace function public.nivel_por_pontos(p_pontos integer)
returns text
language sql
immutable
set search_path = ''
as $$
  select coalesce(
    (select n ->> 'nome'
       from jsonb_array_elements(public.regras_limites() -> 'niveis') n
      where (n ->> 'de')::integer <= p_pontos
      order by (n ->> 'de')::integer desc
      limit 1),
    public.regras_limites() -> 'niveis' -> 0 ->> 'nome'
  );
$$;

revoke all on function public.nivel_por_pontos(integer) from public, anon, authenticated;
grant execute on function public.nivel_por_pontos(integer) to authenticated;

-- ---------------------------------------------------------------------
-- registrar_descarte
-- Regras (todas no banco, nada vem do cliente além do que o usuário informou):
--  1. exige usuário logado
--  2. quantidade de 1 até quantidade_max
--  3. o usuário precisa estar a no máximo raio_m do ponto (Haversine, com as
--     coordenadas do ponto guardadas no banco)
--  4. no máximo max_registros e max_itens por dia (dia de Brasília) por usuário
--  5. pontos e peso saem de tipos_residuo × quantidade
--  6. medalhas (07) são concedidas aqui dentro, nunca pelo cliente, e não dão pontos
-- Todos os números vêm de regras_limites().
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
  v_regras        constant jsonb := public.regras_limites();
  c_raio_max_m    constant double precision := (v_regras ->> 'raio_m')::double precision;
  c_max_registros constant integer := (v_regras ->> 'max_registros')::integer;
  c_max_itens     constant integer := (v_regras ->> 'max_itens')::integer;
  c_quantidade_max constant integer := (v_regras ->> 'quantidade_max')::integer;
  c_tz            constant text := v_regras ->> 'fuso';

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
  v_novas     jsonb := '[]'::jsonb;
begin
  if v_uid is null then
    raise exception 'Entre na sua conta para registrar um descarte.' using hint = 'nao_logado';
  end if;

  if p_quantidade is null or p_quantidade < 1 or p_quantidade > c_quantidade_max then
    raise exception 'A quantidade deve ser de 1 a % itens.', c_quantidade_max using hint = 'quantidade_invalida';
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
    raise exception 'Você precisa estar a até % m do ponto de coleta para registrar o descarte.', c_raio_max_m::integer
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
    raise exception 'Você já fez % registros hoje. Volte amanhã.', c_max_registros using hint = 'limite_registros';
  end if;
  if v_itens + p_quantidade > c_max_itens then
    if v_itens >= c_max_itens then
      raise exception 'O limite é de % itens por dia. Volte amanhã.', c_max_itens using hint = 'limite_itens';
    end if;
    raise exception 'O limite é de % itens por dia. Você ainda pode registrar % hoje.', c_max_itens, c_max_itens - v_itens
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

  -- Medalhas (07): quem concede é o banco, depois do descarte gravado. Medalha não altera pontos_total.
  -- Se o 07 ainda não foi aplicado, a função não existe e simplesmente não há medalha.
  if to_regprocedure('public.conceder_medalhas(uuid)') is not null then
    execute 'select public.conceder_medalhas($1)' into v_novas using v_uid;
  end if;

  return jsonb_build_object(
    'descarte_id',      v_id,
    'pontos_ganhos',    v_pontos,
    'pontos_total',     v_total,
    'nivel',            public.nivel_por_pontos(v_total),
    'peso_kg_estimado', v_peso,
    'medalhas_novas',   v_novas
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

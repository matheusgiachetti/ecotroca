"""
supabase/06-ranking.sql contra um Postgres LOCAL descartável (pgserver), sem tocar no banco do projeto.

Aplica schema.sql e 02 a 06 (duas vezes, para provar que são idempotentes) num banco vazio, com um
"auth" mínimo no lugar do Supabase (auth.users, auth.uid() e os papéis anon/authenticated), e testa
as regras do ranking: ordem, empate, períodos (fuso de Brasília), cidade, limite, privacidade e
permissões. Precisa de:  python -m pip install pgserver "psycopg[binary]" tzdata
Sem essas bibliotecas, os testes são pulados.
"""

import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")
ZoneInfo = pytest.importorskip("zoneinfo").ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVOS = ["schema.sql", "02-perfis.sql", "03-tipos-residuo.sql", "04-descartes.sql", "05-rpc-pontos.sql", "06-ranking.sql"]
BRASILIA = ZoneInfo("America/Sao_Paulo")

AUTH_MINIMO = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
end $$;
create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(), email text, raw_user_meta_data jsonb not null default '{}');
create or replace function auth.uid() returns uuid language sql stable as
  $f$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
"""


def garantir_fusos_horarios():
    """O Postgres embutido do Windows não traz os fusos horários. Copia os do pacote `tzdata`
    (mesmo formato TZif) para a pasta de compartilhamento dele, uma vez, antes de subir o servidor.
    Só mexe na instalação do pgserver, nunca no repositório nem no banco do projeto."""
    tzdata = pytest.importorskip("tzdata")
    destino = Path(pgserver.__file__).parent / "pginstall" / "share" / "postgresql" / "timezone"
    if not (destino / "America" / "Sao_Paulo").exists():
        shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", destino, dirs_exist_ok=True)


@pytest.fixture(scope="module")
def bd():
    garantir_fusos_horarios()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        servidor = pgserver.get_server(pasta, cleanup_mode="stop")
        with psycopg.connect(servidor.get_uri(), autocommit=True) as conexao:
            conexao.execute(AUTH_MINIMO)
            for rodada in (1, 2):  # a segunda rodada prova a idempotência
                for arquivo in ARQUIVOS:
                    conexao.execute((RAIZ / "supabase" / arquivo).read_text(encoding="utf-8"))
            yield conexao
        servidor.cleanup()


# ---------------------------------------------------------------------
# ajudantes
# ---------------------------------------------------------------------
def novo_usuario(bd, apelido, cidade="Sorocaba"):
    uid = bd.execute("insert into auth.users (email, raw_user_meta_data) values (%s, %s::jsonb) returning id",
                     (f"{apelido}@example.com", f'{{"apelido": "{apelido}"}}')).fetchone()[0]
    bd.execute("update public.profiles set cidade = %s where id = %s", (cidade, uid))
    return uid


def descarte(bd, uid, pontos, quando=None):
    """Insere um descarte direto (como administrador) numa data escolhida."""
    bd.execute(
        """insert into public.descartes (user_id, tipo_id, quantidade, pontos, peso_kg_estimado, criado_em)
           values (%s, (select min(id) from public.tipos_residuo), 1, %s, 0.1, coalesce(%s, now()))""",
        (uid, pontos, quando))


def como(bd, papel, uid=None):
    bd.execute(f"set role {papel}")
    bd.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(uid) if uid else "",))


def voltar(bd):
    bd.execute("reset role")


def consultar(bd, sql, args=(), papel="anon", uid=None):
    como(bd, papel, uid)
    try:
        return bd.execute(sql, args).fetchall()
    finally:
        voltar(bd)


def ranking(bd, periodo="geral", cidade=None, limite=10, papel="anon"):
    return consultar(bd, "select posicao, apelido, cidade, pontos from public.ranking(%s, %s, %s)",
                     (periodo, cidade, limite), papel)


def cidade_unica():
    return "Cidade" + uuid.uuid4().hex[:8]


def limites_do_periodo():
    """Início da semana (segunda 00:00) e do mês, em Brasília, calculados em Python."""
    agora = datetime.now(BRASILIA)
    semana = (agora - timedelta(days=agora.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return semana, mes


# ---------------------------------------------------------------------
# Ordem, posição e quem aparece
# ---------------------------------------------------------------------
def test_ordem_por_pontos_e_desempate_pelo_apelido(bd):
    cidade = cidade_unica()
    for apelido, pontos in (("zeca", 50), ("bruno", 60), ("ana", 10), ("beto", 60), ("carla", 50)):
        descarte(bd, novo_usuario(bd, apelido, cidade), pontos)
    linhas = ranking(bd, "geral", cidade)
    assert linhas == [(1, "beto", cidade, 60), (2, "bruno", cidade, 60), (3, "carla", cidade, 50),
                      (4, "zeca", cidade, 50), (5, "ana", cidade, 10)]


def test_soma_varios_descartes_e_ignora_quem_nao_pontuou(bd):
    cidade = cidade_unica()
    a = novo_usuario(bd, "soma_a", cidade)
    for p in (5, 20, 50):
        descarte(bd, a, p)
    novo_usuario(bd, "sem_pontos", cidade)  # tem perfil, nunca descartou
    assert ranking(bd, "geral", cidade) == [(1, "soma_a", cidade, 75)]


def test_estado_vazio(bd):
    assert ranking(bd, "geral", cidade_unica()) == []
    assert ranking(bd, "semana", cidade_unica()) == []


# ---------------------------------------------------------------------
# Períodos no fuso de Brasília
# ---------------------------------------------------------------------
def test_periodos_semana_mes_e_geral(bd):
    semana, mes = limites_do_periodo()
    assert semana.weekday() == 0  # semana começa na segunda
    cidade = cidade_unica()
    casos = {  # apelido: instante do único descarte
        "agora": datetime.now(BRASILIA),
        "na_segunda_zero_hora": semana,
        "dom_23h30_anterior": semana - timedelta(minutes=30),  # 02:30 UTC de segunda: ainda é a semana passada
        "dia_1_zero_hora": mes,
        "mes_passado": mes - timedelta(minutes=1),
        "ha_dois_anos": datetime.now(BRASILIA) - timedelta(days=730),
    }
    for apelido, quando in casos.items():
        descarte(bd, novo_usuario(bd, apelido, cidade), 10, quando)

    def apelidos(periodo):
        return {l[1] for l in ranking(bd, periodo, cidade, 50)}

    esperado_semana = {a for a, q in casos.items() if q >= semana}
    esperado_mes = {a for a, q in casos.items() if q >= mes}
    assert apelidos("semana") == esperado_semana
    assert apelidos("mes") == esperado_mes
    assert apelidos("geral") == set(casos)
    assert "dom_23h30_anterior" not in apelidos("semana")
    assert "na_segunda_zero_hora" in apelidos("semana")  # limite inclusivo
    assert "dia_1_zero_hora" in apelidos("mes") and "mes_passado" not in apelidos("mes")


def test_pontos_do_periodo_so_somam_o_periodo(bd):
    semana, _ = limites_do_periodo()
    cidade = cidade_unica()
    u = novo_usuario(bd, "dois_periodos", cidade)
    descarte(bd, u, 100, semana - timedelta(days=3))  # semana passada
    descarte(bd, u, 5)                                 # agora
    assert ranking(bd, "geral", cidade) == [(1, "dois_periodos", cidade, 105)]
    assert ranking(bd, "semana", cidade) == [(1, "dois_periodos", cidade, 5)]


def test_periodo_invalido_e_recusado_com_hint(bd):
    for periodo in ("ano", "", "SEMANA", None):
        with pytest.raises(psycopg.errors.RaiseException) as erro:
            ranking(bd, periodo, None)
        assert erro.value.diag.message_hint == "periodo_invalido"


# ---------------------------------------------------------------------
# Cidade
# ---------------------------------------------------------------------
def test_filtro_de_cidade_e_posicao_dentro_do_filtro(bd):
    a, b = cidade_unica(), cidade_unica()
    descarte(bd, novo_usuario(bd, "cid_a1", a), 30)
    descarte(bd, novo_usuario(bd, "cid_a2", a), 20)
    descarte(bd, novo_usuario(bd, "cid_b1", b), 90)
    assert ranking(bd, "geral", a) == [(1, "cid_a1", a, 30), (2, "cid_a2", a, 20)]
    assert ranking(bd, "geral", b) == [(1, "cid_b1", b, 90)]
    # sem filtro, as três aparecem, na ordem global
    todos = [l for l in ranking(bd, "geral", None, 50) if l[1].startswith("cid_")]
    assert [l[1] for l in todos] == ["cid_b1", "cid_a1", "cid_a2"]


@pytest.mark.parametrize("filtro", [lambda c: c.upper(), lambda c: c.lower(), lambda c: f"  {c}  "])
def test_cidade_ignora_maiusculas_e_espacos(bd, filtro):
    cidade = cidade_unica()
    descarte(bd, novo_usuario(bd, "caixa_" + uuid.uuid4().hex[:6], cidade), 10)
    assert len(ranking(bd, "geral", filtro(cidade))) == 1


def test_cidade_nula_ou_em_branco_significa_todas(bd):
    cidade = cidade_unica()
    descarte(bd, novo_usuario(bd, "todas_" + uuid.uuid4().hex[:6], cidade), 10)
    assert {l[1] for l in ranking(bd, "geral", None, 50)} == {l[1] for l in ranking(bd, "geral", "   ", 50)}


# ---------------------------------------------------------------------
# Limite
# ---------------------------------------------------------------------
def test_limite_padrao_maximo_e_valores_invalidos(bd):
    cidade = cidade_unica()
    for i in range(55):
        descarte(bd, novo_usuario(bd, f"lim_{i:02d}", cidade), 100 - i)
    assert len(ranking(bd, "geral", cidade, 3)) == 3
    assert len(ranking(bd, "geral", cidade, 10)) == 10
    for invalido in (None, 0, -1, -50):
        assert len(ranking(bd, "geral", cidade, invalido)) == 10, invalido  # volta ao padrão
    assert len(ranking(bd, "geral", cidade, 51)) == 50   # no máximo 50
    assert len(ranking(bd, "geral", cidade, 9999)) == 50
    # padrão da assinatura: sem informar o limite, são 10
    assert len(consultar(bd, "select * from public.ranking('geral', %s)", (cidade,))) == 10


# ---------------------------------------------------------------------
# Privacidade e permissões
# ---------------------------------------------------------------------
def test_ranking_devolve_so_posicao_apelido_cidade_e_pontos(bd):
    descarte(bd, novo_usuario(bd, "privacidade", cidade_unica()), 10)
    como(bd, "anon")
    try:
        cursor = bd.execute("select * from public.ranking('geral', null, 5)")
        assert [c.name for c in cursor.description] == ["posicao", "apelido", "cidade", "pontos"]
    finally:
        voltar(bd)


def test_anonimo_nao_le_nem_escreve_nas_tabelas(bd):
    uid = novo_usuario(bd, "fechada_anon", cidade_unica())
    descarte(bd, uid, 10)
    for tabela in ("public.descartes", "public.profiles"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            consultar(bd, f"select * from {tabela}", papel="anon")
    for escrita in ("insert into public.descartes (user_id, tipo_id, quantidade, pontos, peso_kg_estimado) values (gen_random_uuid(), 1, 1, 1, 1)",
                    "update public.profiles set pontos_total = 99999"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            consultar(bd, escrita, papel="anon")


def test_logado_so_ve_os_proprios_dados_e_nao_escreve(bd):
    cidade = cidade_unica()
    dono = novo_usuario(bd, "fechada_dono", cidade)
    outro = novo_usuario(bd, "fechada_outro", cidade)
    descarte(bd, dono, 10)
    # RLS: "outro" não enxerga o descarte nem o perfil do "dono", mesmo com o ranking público aberto
    assert consultar(bd, "select * from public.descartes where user_id = %s", (dono,), "authenticated", outro) == []
    assert consultar(bd, "select id from public.profiles where id = %s", (dono,), "authenticated", outro) == []
    assert len(consultar(bd, "select * from public.descartes where user_id = %s", (dono,), "authenticated", dono)) == 1
    for escrita in ("insert into public.descartes (user_id, tipo_id, quantidade, pontos, peso_kg_estimado) values (gen_random_uuid(), 1, 1, 1, 1)",
                    "update public.profiles set pontos_total = 99999"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            consultar(bd, escrita, papel="authenticated", uid=dono)


def test_permissoes_de_execucao(bd):
    def executa(papel, assinatura):
        return bd.execute("select has_function_privilege(%s, %s, 'execute')", (papel, assinatura)).fetchone()[0]

    r, m, l = "public.ranking(text,text,integer)", "public.minha_posicao(text,text)", "public.ranking_linhas(text,text)"
    assert executa("anon", r) and executa("authenticated", r)       # leitura pública
    assert not executa("anon", m) and executa("authenticated", m)   # só logado
    assert not executa("anon", l) and not executa("authenticated", l)  # auxiliar interna
    assert not executa("public", r) and not executa("public", m) and not executa("public", l)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        consultar(bd, "select * from public.minha_posicao('geral', null)", papel="anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        consultar(bd, "select * from public.ranking_linhas('geral', null)", papel="authenticated")


def test_funcoes_com_search_path_fixo_e_security_definer(bd):
    linhas = bd.execute("""select proname, prosecdef, proconfig from pg_proc
                            where pronamespace = 'public'::regnamespace and proname in ('ranking', 'minha_posicao', 'ranking_linhas')""").fetchall()
    por_nome = {n: (d, c) for n, d, c in linhas}
    assert por_nome["ranking"][0] and por_nome["minha_posicao"][0]
    assert all(c and 'search_path=""' in c for _, c in por_nome.values())


# ---------------------------------------------------------------------
# minha_posicao
# ---------------------------------------------------------------------
def test_minha_posicao(bd):
    cidade, outra = cidade_unica(), cidade_unica()
    primeiro = novo_usuario(bd, "mp_primeiro", cidade)
    segundo = novo_usuario(bd, "mp_segundo", cidade)
    de_fora = novo_usuario(bd, "mp_de_fora", outra)
    sem_pontos = novo_usuario(bd, "mp_zero", cidade)
    descarte(bd, primeiro, 80)
    descarte(bd, segundo, 30)
    descarte(bd, de_fora, 500)

    def minha(uid, periodo="geral", c=cidade):
        return consultar(bd, "select posicao, pontos from public.minha_posicao(%s, %s)", (periodo, c), "authenticated", uid)

    assert minha(primeiro) == [(1, 80)]
    assert minha(segundo) == [(2, 30)]
    assert minha(sem_pontos) == []                      # não pontuou: nenhuma linha
    assert minha(de_fora) == []                         # fora do filtro de cidade
    assert minha(de_fora, c=outra) == [(1, 500)]
    # coerente com o ranking público
    assert [l[0] for l in ranking(bd, "geral", cidade) if l[1] == "mp_segundo"] == [2]


def test_minha_posicao_sem_login_e_recusada(bd):
    como(bd, "authenticated", None)  # papel logado, mas sem usuário no token
    try:
        with pytest.raises(psycopg.errors.RaiseException) as erro:
            bd.execute("select * from public.minha_posicao('geral', null)").fetchall()
        assert erro.value.diag.message_hint == "nao_logado"
    finally:
        voltar(bd)


def test_minha_posicao_periodo_invalido(bd):
    uid = novo_usuario(bd, "mp_periodo", cidade_unica())
    with pytest.raises(psycopg.errors.RaiseException) as erro:
        consultar(bd, "select * from public.minha_posicao('ano', null)", papel="authenticated", uid=uid)
    assert erro.value.diag.message_hint == "periodo_invalido"


# ---------------------------------------------------------------------
# Ponta a ponta: registrar_descarte (05) alimenta o ranking (06)
# ---------------------------------------------------------------------
def test_registrar_descarte_alimenta_o_ranking(bd):
    cidade = cidade_unica()
    uid = novo_usuario(bd, "ponta_a_ponta", cidade)
    ponto = bd.execute(
        "insert into public.pontos_coleta (nome, endereco, latitude, longitude) values ('Local de teste', 'Rua X', -23.5, -47.45) returning id"
    ).fetchone()[0]
    celulares = bd.execute("select id from public.tipos_residuo where nome = 'Celulares'").fetchone()[0]
    como(bd, "authenticated", uid)
    try:
        # 0,0005° de latitude ≈ 55 m do ponto
        r = bd.execute("select public.registrar_descarte(%s, %s, 2, -23.4995, -47.45)", (ponto, celulares)).fetchone()[0]
    finally:
        voltar(bd)
    assert r["pontos_ganhos"] == 40
    assert ranking(bd, "semana", cidade) == [(1, "ponta_a_ponta", cidade, 40)]
    assert ranking(bd, "mes", cidade) == ranking(bd, "geral", cidade) == [(1, "ponta_a_ponta", cidade, 40)]

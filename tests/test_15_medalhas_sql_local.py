"""
supabase/05-rpc-pontos.sql + supabase/07-medalhas.sql contra um Postgres LOCAL descartável (pgserver),
sem tocar no banco do projeto. Mesmo esquema de tests/test_14_ranking_sql_local.py.

Cobre: concessão de medalhas só na hora certa (1º descarte, 10 itens, 3 tipos, 100 pontos), sem repetir,
medalha não mexe em pontos_total, permissões e RLS, regras_pontos() batendo com tipos_residuo e com as
regras de registrar_descarte, e a idempotência (05 a 07 aplicados duas vezes).
Precisa de:  python -m pip install pgserver "psycopg[binary]" tzdata   (sem elas, os testes são pulados)
"""

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

RAIZ = Path(__file__).resolve().parent.parent
BASE = ["schema.sql", "02-perfis.sql", "03-tipos-residuo.sql", "04-descartes.sql", "05-rpc-pontos.sql"]
ARQUIVOS = BASE + ["06-ranking.sql", "07-medalhas.sql"]

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
grant usage on schema auth to anon, authenticated;  -- como no Supabase (funções invoker chamam auth.uid())
"""

PONTO_LAT, PONTO_LNG = -23.5, -47.45
PRIMEIRO, DEZ, TRES, CEM = "Primeiro descarte", "10 itens descartados", "3 tipos de resíduo", "100 pontos"


def garantir_fusos_horarios():
    tzdata = pytest.importorskip("tzdata")
    destino = Path(pgserver.__file__).parent / "pginstall" / "share" / "postgresql" / "timezone"
    if not (destino / "America" / "Sao_Paulo").exists():
        shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", destino, dirs_exist_ok=True)


def banco_novo(arquivos, rodadas):
    garantir_fusos_horarios()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        servidor = pgserver.get_server(pasta, cleanup_mode="stop")
        with psycopg.connect(servidor.get_uri(), autocommit=True) as conexao:
            conexao.execute(AUTH_MINIMO)
            for _ in range(rodadas):  # a segunda rodada prova a idempotência
                for arquivo in arquivos:
                    conexao.execute((RAIZ / "supabase" / arquivo).read_text(encoding="utf-8"))
            yield conexao
        servidor.cleanup()


@pytest.fixture(scope="module")
def bd():
    yield from banco_novo(ARQUIVOS, 2)


# ---------------------------------------------------------------------
# ajudantes
# ---------------------------------------------------------------------
def novo_usuario(bd, apelido=None):
    apelido = apelido or "u" + uuid.uuid4().hex[:10]
    return bd.execute("insert into auth.users (email, raw_user_meta_data) values (%s, %s::jsonb) returning id",
                      (f"{apelido}@example.com", f'{{"apelido": "{apelido}"}}')).fetchone()[0]


def como(bd, papel, uid=None):
    bd.execute(f"set role {papel}")
    bd.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(uid) if uid else "",))


def consultar(bd, sql, args=(), papel="authenticated", uid=None):
    como(bd, papel, uid)
    try:
        return bd.execute(sql, args).fetchall()
    finally:
        bd.execute("reset role")


@pytest.fixture(scope="module")
def ponto(bd):
    return bd.execute("insert into public.pontos_coleta (nome, endereco, latitude, longitude) "
                      "values ('Local de teste', 'Rua X', %s, %s) returning id", (PONTO_LAT, PONTO_LNG)).fetchone()[0]


@pytest.fixture(scope="module")
def tipo(bd):
    """nome -> id"""
    return {n: i for i, n in bd.execute("select id, nome from public.tipos_residuo").fetchall()}


def registrar(bd, uid, ponto_id, tipo_id, qtd, dlat=0.0):
    return consultar(bd, "select public.registrar_descarte(%s, %s, %s, %s, %s)",
                     (ponto_id, tipo_id, qtd, PONTO_LAT + dlat, PONTO_LNG), "authenticated", uid)[0][0]


def hint_de(bd, uid, ponto_id, tipo_id, qtd, dlat=0.0):
    with pytest.raises(psycopg.errors.RaiseException) as erro:
        registrar(bd, uid, ponto_id, tipo_id, qtd, dlat)
    return erro.value.diag.message_hint, erro.value.diag.message_primary


def medalhas_do(bd, uid):
    return {c for (c,) in bd.execute("select medalha_codigo from public.usuario_medalhas where user_id = %s", (uid,)).fetchall()}


def pontos_total(bd, uid):
    return bd.execute("select pontos_total from public.profiles where id = %s", (uid,)).fetchone()[0]


# ---------------------------------------------------------------------
# Concessão: só na hora certa, uma vez só
# ---------------------------------------------------------------------
def test_primeiro_descarte_concede_so_a_primeira_medalha(bd, ponto, tipo):
    u = novo_usuario(bd)
    r = registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)
    assert r["medalhas_novas"] == [PRIMEIRO]
    assert medalhas_do(bd, u) == {"primeiro_descarte"}


def test_nao_concede_duas_vezes(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)
    r = registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)
    assert r["medalhas_novas"] == []
    assert bd.execute("select count(*) from public.usuario_medalhas where user_id = %s", (u,)).fetchone()[0] == 1


def test_dez_itens_so_no_decimo_item(bd, ponto, tipo):
    u = novo_usuario(bd)
    assert registrar(bd, u, ponto, tipo["Pilhas e baterias"], 9)["medalhas_novas"] == [PRIMEIRO]  # 9 itens: ainda não
    assert "dez_itens" not in medalhas_do(bd, u)
    assert registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)["medalhas_novas"] == [DEZ]        # 10º item
    assert registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)["medalhas_novas"] == []


def test_tres_tipos_so_no_terceiro_tipo(bd, ponto, tipo):
    u = novo_usuario(bd)
    assert registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)["medalhas_novas"] == [PRIMEIRO]
    assert registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)["medalhas_novas"] == []  # mesmo tipo: não conta
    assert registrar(bd, u, ponto, tipo["Cabos e carregadores"], 1)["medalhas_novas"] == []  # 2 tipos
    assert registrar(bd, u, ponto, tipo["Celulares"], 1)["medalhas_novas"] == [TRES]          # 3 tipos
    assert "cem_pontos" not in medalhas_do(bd, u)  # 5+5+5+20 = 35 pontos


def test_cem_pontos_so_ao_chegar_em_100(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Computadores e periféricos"], 1)   # 50
    registrar(bd, u, ponto, tipo["Eletrodomésticos pequenos"], 1)    # 80
    r = registrar(bd, u, ponto, tipo["Pilhas e baterias"], 3)        # 95 (e é o 3º tipo)
    assert r["pontos_total"] == 95 and "cem_pontos" not in medalhas_do(bd, u)
    r = registrar(bd, u, ponto, tipo["Pilhas e baterias"], 1)        # 100
    assert r["pontos_total"] == 100 and r["medalhas_novas"] == [CEM]


def test_varias_de_uma_vez_vem_na_ordem_do_catalogo(bd, ponto, tipo):
    u = novo_usuario(bd)
    r = registrar(bd, u, ponto, tipo["Computadores e periféricos"], 2)  # 100 pontos de uma vez
    assert r["medalhas_novas"] == [PRIMEIRO, CEM]


def test_medalha_nao_altera_pontos(bd, ponto, tipo):
    u = novo_usuario(bd)
    r = registrar(bd, u, ponto, tipo["Computadores e periféricos"], 2)
    assert r["medalhas_novas"] and r["pontos_ganhos"] == 100 and r["pontos_total"] == 100
    registrar(bd, u, ponto, tipo["Pilhas e baterias"], 8)
    soma = bd.execute("select sum(pontos) from public.descartes where user_id = %s", (u,)).fetchone()[0]
    assert pontos_total(bd, u) == soma == 140  # só os descartes contam, não as 3 medalhas


def test_falha_de_regra_nao_concede_nada(bd, ponto, tipo):
    u = novo_usuario(bd)
    assert hint_de(bd, u, ponto, tipo["Celulares"], 1, dlat=0.01)[0] == "longe_do_ponto"
    assert medalhas_do(bd, u) == set()


def test_resposta_traz_medalhas_novas_como_lista_de_nomes(bd, ponto, tipo):
    r = registrar(bd, novo_usuario(bd), ponto, tipo["Celulares"], 1)
    assert isinstance(r["medalhas_novas"], list) and all(isinstance(n, str) for n in r["medalhas_novas"])
    assert set(r) == {"descarte_id", "pontos_ganhos", "pontos_total", "nivel", "peso_kg_estimado", "medalhas_novas"}


# ---------------------------------------------------------------------
# minhas_medalhas, RLS e permissões
# ---------------------------------------------------------------------
def test_minhas_medalhas_lista_todas_com_conquistada(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Computadores e periféricos"], 2)
    linhas = consultar(bd, "select codigo, nome, conquistada, conquistada_em is not null from public.minhas_medalhas()", uid=u)
    assert [l[0] for l in linhas] == ["primeiro_descarte", "dez_itens", "tres_tipos", "cem_pontos"]
    assert [(l[0], l[2], l[3]) for l in linhas] == [("primeiro_descarte", True, True), ("dez_itens", False, False),
                                                     ("tres_tipos", False, False), ("cem_pontos", True, True)]


def test_logado_so_ve_as_proprias(bd, ponto, tipo):
    dono, outro = novo_usuario(bd), novo_usuario(bd)
    registrar(bd, dono, ponto, tipo["Celulares"], 1)
    assert consultar(bd, "select * from public.usuario_medalhas where user_id = %s", (dono,), uid=outro) == []
    assert len(consultar(bd, "select * from public.usuario_medalhas where user_id = %s", (dono,), uid=dono)) == 1
    assert [l[0] for l in consultar(bd, "select conquistada from public.minhas_medalhas()", uid=outro)] == [False] * 4


def test_anonimo_nao_le_nada_de_medalhas(bd, ponto, tipo):
    registrar(bd, novo_usuario(bd), ponto, tipo["Celulares"], 1)
    for sql in ("select * from public.usuario_medalhas", "select * from public.medalhas", "select * from public.minhas_medalhas()"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            consultar(bd, sql, papel="anon")


def test_ninguem_escreve_direto(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Celulares"], 1)
    escritas = [
        "insert into public.usuario_medalhas (user_id, medalha_codigo) values ('%s', 'cem_pontos')" % u,
        "update public.usuario_medalhas set medalha_codigo = 'cem_pontos'",
        "delete from public.usuario_medalhas",
        "insert into public.medalhas (codigo, nome, descricao) values ('falsa', 'Falsa', 'x')",
        "update public.medalhas set nome = 'x'",
        "delete from public.medalhas",
    ]
    for papel in ("anon", "authenticated"):
        for sql in escritas:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                consultar(bd, sql, papel=papel, uid=u if papel == "authenticated" else None)
    assert medalhas_do(bd, u) == {"primeiro_descarte"}


def test_minhas_medalhas_sem_usuario_no_token_e_recusada(bd):
    como(bd, "authenticated", None)
    try:
        with pytest.raises(psycopg.errors.RaiseException) as erro:
            bd.execute("select * from public.minhas_medalhas()").fetchall()
        assert erro.value.diag.message_hint == "nao_logado"
    finally:
        bd.execute("reset role")


def test_permissoes_de_execucao_e_search_path(bd):
    def executa(papel, assinatura):
        return bd.execute("select has_function_privilege(%s, %s, 'execute')", (papel, assinatura)).fetchone()[0]

    conceder, minhas, regras = "public.conceder_medalhas(uuid)", "public.minhas_medalhas()", "public.regras_pontos()"
    for papel in ("anon", "authenticated", "public"):
        assert not executa(papel, conceder)                    # só registrar_descarte chama
    assert not executa("anon", minhas) and executa("authenticated", minhas)
    assert executa("anon", regras) and executa("authenticated", regras)
    assert not executa("anon", "public.regras_limites()")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        consultar(bd, "select public.conceder_medalhas(gen_random_uuid())", papel="authenticated", uid=novo_usuario(bd))
    linhas = bd.execute("""select proname, proconfig from pg_proc where pronamespace = 'public'::regnamespace
                           and proname in ('conceder_medalhas', 'minhas_medalhas', 'regras_pontos', 'regras_limites', 'registrar_descarte')""").fetchall()
    assert len(linhas) == 5 and all(c and 'search_path=""' in c for _, c in linhas)


# ---------------------------------------------------------------------
# regras_pontos: uma fonte só
# ---------------------------------------------------------------------
def test_regras_pontos_bate_com_tipos_e_catalogo(bd):
    regras = consultar(bd, "select public.regras_pontos()", papel="anon")[0][0]
    tipos_banco = bd.execute("select nome, pontos from public.tipos_residuo order by id").fetchall()
    assert [(t["nome"], t["pontos"]) for t in regras["tipos"]] == tipos_banco
    medalhas_banco = bd.execute("select nome, descricao from public.medalhas order by ordem").fetchall()
    assert [(m["nome"], m["descricao"]) for m in regras["medalhas"]] == medalhas_banco
    assert set(regras) == {"tipos", "raio_m", "max_registros", "max_itens", "quantidade_max", "fuso", "niveis", "medalhas"}
    assert set(regras["medalhas"][0]) == {"nome", "descricao"}  # sem códigos internos nem dados de ninguém
    assert regras["raio_m"] == 200 and regras["max_registros"] == 5 and regras["max_itens"] == 30
    assert regras["fuso"] == "America/Sao_Paulo"
    assert consultar(bd, "select public.regras_pontos()", papel="authenticated")[0][0] == regras


def test_niveis_de_regras_pontos_batem_com_nivel_por_pontos(bd):
    regras = consultar(bd, "select public.regras_pontos()", papel="anon")[0][0]
    assert [(n["nome"], n["de"]) for n in regras["niveis"]] == [
        ("Semente", 0), ("Broto", 50), ("Muda", 150), ("Árvore", 350), ("Floresta", 700)]
    for i, n in enumerate(regras["niveis"]):
        assert bd.execute("select public.nivel_por_pontos(%s)", (n["de"],)).fetchone()[0] == n["nome"]
        if n["de"] > 0:  # um ponto abaixo do limite ainda é o nível anterior
            assert bd.execute("select public.nivel_por_pontos(%s)", (n["de"] - 1,)).fetchone()[0] == regras["niveis"][i - 1]["nome"]
    assert bd.execute("select public.nivel_por_pontos(-5)").fetchone()[0] == "Semente"


def test_registrar_descarte_obedece_as_regras_publicadas(bd, ponto, tipo):
    regras = consultar(bd, "select public.regras_pontos()", papel="anon")[0][0]
    pilhas = tipo["Pilhas e baterias"]

    # raio: um pouco dentro passa, um pouco fora não (0,0001° de latitude ≈ 11,1 m)
    u = novo_usuario(bd)
    dentro = (regras["raio_m"] - 15) / 111_195
    fora = (regras["raio_m"] + 15) / 111_195
    registrar(bd, u, ponto, pilhas, 1, dlat=dentro)
    hint, mensagem = hint_de(bd, u, ponto, pilhas, 1, dlat=fora)
    assert hint == "longe_do_ponto" and f"{regras['raio_m']} m" in mensagem

    # registros por dia (a mensagem vem do banco, já com o número da regra)
    u = novo_usuario(bd)
    for _ in range(regras["max_registros"]):
        registrar(bd, u, ponto, pilhas, 1)
    hint, mensagem = hint_de(bd, u, ponto, pilhas, 1)
    assert hint == "limite_registros" and str(regras["max_registros"]) in mensagem

    # itens por dia
    u = novo_usuario(bd)
    for _ in range(regras["max_itens"] // regras["quantidade_max"]):
        registrar(bd, u, ponto, pilhas, regras["quantidade_max"])
    hint, mensagem = hint_de(bd, u, ponto, pilhas, 1)
    assert hint == "limite_itens" and str(regras["max_itens"]) in mensagem

    # quantidade
    hint, mensagem = hint_de(bd, novo_usuario(bd), ponto, pilhas, regras["quantidade_max"] + 1)
    assert hint == "quantidade_invalida" and str(regras["quantidade_max"]) in mensagem


def test_limite_de_itens_diz_quanto_ainda_cabe(bd, ponto, tipo):
    u = novo_usuario(bd)
    for _ in range(2):
        registrar(bd, u, ponto, tipo["Pilhas e baterias"], 10)
    registrar(bd, u, ponto, tipo["Pilhas e baterias"], 8)  # 28 de 30
    assert "ainda pode registrar 2" in hint_de(bd, u, ponto, tipo["Pilhas e baterias"], 3)[1]


# ---------------------------------------------------------------------
# Compatibilidade e idempotência
# ---------------------------------------------------------------------
def test_05_sem_o_07_continua_registrando_sem_medalhas():
    """A ordem de aplicação não derruba o site: sem o 07, registrar_descarte funciona e não concede nada."""
    gerador = banco_novo(ARQUIVOS[:-1] , 1)  # schema, 02 a 06
    bd2 = next(gerador)
    try:
        uid = novo_usuario(bd2)
        ponto_id = bd2.execute("insert into public.pontos_coleta (nome, endereco, latitude, longitude) values ('L', 'R', %s, %s) returning id",
                               (PONTO_LAT, PONTO_LNG)).fetchone()[0]
        celulares = bd2.execute("select id from public.tipos_residuo where nome = 'Celulares'").fetchone()[0]
        r = registrar(bd2, uid, ponto_id, celulares, 1)
        assert r["pontos_ganhos"] == 20 and r["medalhas_novas"] == []
        # aplicar o 07 depois: o próximo descarte já concede
        bd2.execute((RAIZ / "supabase" / "07-medalhas.sql").read_text(encoding="utf-8"))
        assert registrar(bd2, uid, ponto_id, celulares, 1)["medalhas_novas"] == [PRIMEIRO]
    finally:
        gerador.close()


def test_aplicar_duas_vezes_nao_apaga_conquistas_nem_duplica_catalogo(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Celulares"], 1)
    for arquivo in ("05-rpc-pontos.sql", "06-ranking.sql", "07-medalhas.sql"):
        bd.execute((RAIZ / "supabase" / arquivo).read_text(encoding="utf-8"))
    assert medalhas_do(bd, u) == {"primeiro_descarte"}
    assert bd.execute("select count(*) from public.medalhas").fetchone()[0] == 4

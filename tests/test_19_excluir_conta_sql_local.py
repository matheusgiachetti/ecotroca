"""
supabase/08-excluir-conta.sql contra um Postgres LOCAL descartável (pgserver), sem tocar no banco do projeto.
Aplica schema.sql e 02 a 08 (duas vezes, para provar a idempotência) com um "auth" mínimo no lugar do Supabase.

Prova: só a própria pessoa se exclui; perfil, descartes e medalhas saem em cascata, sem dados órfãos; os dados
das outras pessoas e os pontos de coleta ficam intactos; anon não executa; o apelido libera para reuso.
Precisa de:  python -m pip install pgserver "psycopg[binary]" tzdata   (sem elas, os testes são pulados)
"""

import uuid

import pytest

from test_15_medalhas_sql_local import (  # reaproveita o ambiente do teste das medalhas
    PONTO_LAT, PONTO_LNG, RAIZ, banco_novo, como, consultar, medalhas_do, novo_usuario, registrar,
)

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ARQUIVOS = ["schema.sql", "02-perfis.sql", "03-tipos-residuo.sql", "04-descartes.sql", "05-rpc-pontos.sql",
            "06-ranking.sql", "07-medalhas.sql", "08-excluir-conta.sql"]


@pytest.fixture(scope="module")
def bd():
    yield from banco_novo(ARQUIVOS, 2)  # a segunda rodada prova a idempotência


@pytest.fixture(scope="module")
def ponto(bd):
    return bd.execute("insert into public.pontos_coleta (nome, endereco, latitude, longitude) "
                      "values ('Local de teste', 'Rua X', %s, %s) returning id", (PONTO_LAT, PONTO_LNG)).fetchone()[0]


@pytest.fixture(scope="module")
def tipo(bd):
    return {n: i for i, n in bd.execute("select id, nome from public.tipos_residuo").fetchall()}


def contar(bd, uid):
    """Quantas linhas da pessoa existem em cada tabela."""
    return {
        "auth.users": bd.execute("select count(*) from auth.users where id = %s", (uid,)).fetchone()[0],
        "profiles": bd.execute("select count(*) from public.profiles where id = %s", (uid,)).fetchone()[0],
        "descartes": bd.execute("select count(*) from public.descartes where user_id = %s", (uid,)).fetchone()[0],
        "usuario_medalhas": bd.execute("select count(*) from public.usuario_medalhas where user_id = %s", (uid,)).fetchone()[0],
    }


def excluir(bd, uid):
    return consultar(bd, "select public.excluir_minha_conta()", papel="authenticated", uid=uid)


def test_exclui_a_conta_e_tudo_que_depende_dela(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Computadores e periféricos"], 2)  # 100 pontos: 2 medalhas
    registrar(bd, u, ponto, tipo["Celulares"], 1)
    antes = contar(bd, u)
    assert antes == {"auth.users": 1, "profiles": 1, "descartes": 2, "usuario_medalhas": 2}, antes
    excluir(bd, u)
    assert contar(bd, u) == {"auth.users": 0, "profiles": 0, "descartes": 0, "usuario_medalhas": 0}


def test_nao_sobra_dado_orfao_em_nenhuma_tabela(bd, ponto, tipo):
    u = novo_usuario(bd)
    registrar(bd, u, ponto, tipo["Celulares"], 1)
    excluir(bd, u)
    assert bd.execute("select count(*) from public.descartes d where not exists (select 1 from public.profiles p where p.id = d.user_id)").fetchone()[0] == 0
    assert bd.execute("select count(*) from public.usuario_medalhas m where not exists (select 1 from public.profiles p where p.id = m.user_id)").fetchone()[0] == 0
    assert bd.execute("select count(*) from public.profiles p where not exists (select 1 from auth.users a where a.id = p.id)").fetchone()[0] == 0
    # toda tabela do schema public que tem user_id/id de usuário aponta para uma FK com cascata
    sem_cascata = bd.execute("""
        select c.conrelid::regclass::text from pg_constraint c
         where c.contype = 'f' and c.connamespace = 'public'::regnamespace
           and c.confrelid in ('auth.users'::regclass, 'public.profiles'::regclass) and c.confdeltype <> 'c'""").fetchall()
    assert sem_cascata == []


def test_so_apaga_a_propria_conta_e_nao_mexe_nas_outras(bd, ponto, tipo):
    eu, outra = novo_usuario(bd), novo_usuario(bd)
    registrar(bd, eu, ponto, tipo["Celulares"], 1)
    registrar(bd, outra, ponto, tipo["Celulares"], 1)
    depois_da_outra = contar(bd, outra)
    excluir(bd, eu)
    assert contar(bd, outra) == depois_da_outra and depois_da_outra["profiles"] == 1
    assert medalhas_do(bd, outra) == {"primeiro_descarte"}
    # os pontos de coleta e os tipos continuam
    assert bd.execute("select count(*) from public.pontos_coleta where id = %s", (ponto,)).fetchone()[0] == 1
    assert bd.execute("select count(*) from public.tipos_residuo").fetchone()[0] == 5


def test_a_funcao_nao_recebe_parametro_entao_ninguem_apaga_outra_pessoa(bd):
    linha = bd.execute("select pronargs, prosecdef, proconfig from pg_proc where proname = 'excluir_minha_conta' "
                       "and pronamespace = 'public'::regnamespace").fetchone()
    assert linha[0] == 0 and linha[1] is True and linha[2] and 'search_path=""' in linha[2]


def test_anonimo_nao_executa(bd):
    def executa(papel):
        return bd.execute("select has_function_privilege(%s, 'public.excluir_minha_conta()', 'execute')", (papel,)).fetchone()[0]

    assert executa("authenticated") and not executa("anon") and not executa("public")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        consultar(bd, "select public.excluir_minha_conta()", papel="anon")


def test_sem_usuario_no_token_e_recusado_com_hint(bd):
    antes = bd.execute("select count(*) from auth.users").fetchone()[0]
    como(bd, "authenticated", None)
    try:
        with pytest.raises(psycopg.errors.RaiseException) as erro:
            bd.execute("select public.excluir_minha_conta()")
        assert erro.value.diag.message_hint == "nao_logado"
    finally:
        bd.execute("reset role")
    assert bd.execute("select count(*) from auth.users").fetchone()[0] == antes  # nada foi apagado


def test_apelido_volta_a_ficar_livre_e_ranking_deixa_de_listar(bd, ponto, tipo):
    apelido = "reuso" + uuid.uuid4().hex[:6]
    u = novo_usuario(bd, apelido)
    registrar(bd, u, ponto, tipo["Celulares"], 1)
    no_ranking = lambda: [l[1] for l in consultar(bd, "select posicao, apelido from public.ranking('geral', null, 50)", papel="anon")]
    assert apelido in no_ranking()
    excluir(bd, u)
    assert apelido not in no_ranking()
    novo_usuario(bd, apelido)  # não dá erro de apelido repetido


def test_aplicar_o_08_de_novo_nao_quebra_nada(bd):
    bd.execute((RAIZ / "supabase" / "08-excluir-conta.sql").read_text(encoding="utf-8"))
    u = novo_usuario(bd)
    excluir(bd, u)
    assert contar(bd, u)["auth.users"] == 0

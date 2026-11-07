"""
Sistema de pontos — segurança e regras no banco, só com a chave PÚBLICA (REST, sem navegador).

Os usuários de teste são criados pela API de Auth (a confirmação de e-mail precisa estar
desligada) e têm e-mail "teste-ecotroca-*@example.com". A chave pública NÃO consegue
apagar usuários: depois da rodada, remova-os pelo SQL Editor ou pelo MCP:

    delete from auth.users where email like 'teste-ecotroca-%@example.com';

(profiles e descartes saem junto, por "on delete cascade").
"""

import secrets

import pytest

from conftest import supabase_rest

DOMINIO = "example.com"
SENHA = "senha-de-teste-" + secrets.token_hex(6)
RODADA = secrets.token_hex(3)
EMAILS_CRIADOS = []

# 0,0010° de latitude ≈ 111 m (dentro do raio) · 0,0019° ≈ 211 m (fora) — raio do banco: 200 m
DENTRO = 0.0010
FORA = 0.0019


def _apelido(sufixo):
    return f"t{RODADA}_{sufixo}"  # 11 a 12 caracteres, só letras, números e _


def cadastrar_via_api(sufixo, apelido=None):
    email = f"teste-ecotroca-{RODADA}-{sufixo}@{DOMINIO}"
    EMAILS_CRIADOS.append(email)  # registra antes: se criar mesmo sem querer, o relatório avisa
    status, corpo = supabase_rest(
        "POST", "signup", {"email": email, "password": SENHA, "data": {"apelido": _apelido(sufixo) if apelido is None else apelido}},
        base="auth/v1",
    )
    return email, status, corpo


def entrar_via_api(email):
    return supabase_rest("POST", "token?grant_type=password", {"email": email, "password": SENHA}, base="auth/v1")


class Usuario:
    def __init__(self, sufixo):
        self.sufixo = sufixo
        self.apelido = _apelido(sufixo)
        self.email, status, corpo = cadastrar_via_api(sufixo)
        assert status == 200 and corpo.get("access_token"), (
            f"cadastro de teste falhou ({status}): {corpo}. A confirmação de e-mail está desligada?"
        )
        self.token = corpo["access_token"]
        self.id = corpo["user"]["id"]

    def rest(self, metodo, caminho, corpo=None, prefer=None):
        cab = {"Prefer": prefer} if prefer else None
        return supabase_rest(metodo, caminho, corpo, cabecalhos=cab, token=self.token)

    def rpc(self, nome, args=None):
        return supabase_rest("POST", f"rpc/{nome}", args or {}, token=self.token)


@pytest.fixture(scope="module")
def ponto(pontos_db):
    return pontos_db[0]


@pytest.fixture(scope="module")
def tipos():
    status, linhas = supabase_rest("GET", "tipos_residuo?select=*&order=id")
    assert status == 200
    return {t["nome"]: t for t in linhas}


@pytest.fixture(scope="module")
def ana():
    return Usuario("ana")


@pytest.fixture(scope="module")
def beto():
    return Usuario("beto")


def descartar(usuario, ponto, tipo_id, quantidade, dlat=DENTRO, dlng=0.0, lat=None, lng=None):
    return usuario.rpc("registrar_descarte", {
        "p_ponto_id": ponto["id"], "p_tipo_id": tipo_id, "p_quantidade": quantidade,
        "p_lat": ponto["latitude"] + dlat if lat is None else lat,
        "p_lng": ponto["longitude"] + dlng if lng is None else lng,
    })


def hint(corpo):
    return corpo.get("hint") if isinstance(corpo, dict) else None


# ---------------------------------------------------------------------
# Anônimo
# ---------------------------------------------------------------------
NEGADO = (401, 403)


def test_anonimo_nao_escreve_nem_le_dados_de_conta(ponto, tipos):
    pilhas = tipos["Pilhas e baterias"]["id"]
    zero = "00000000-0000-0000-0000-000000000000"

    status, corpo = supabase_rest("POST", "descartes", {
        "user_id": zero, "ponto_id": ponto["id"], "tipo_id": pilhas, "quantidade": 1, "pontos": 999, "peso_kg_estimado": 1})
    assert status in NEGADO and corpo["code"] == "42501", (status, corpo)

    status, corpo = supabase_rest("PATCH", f"profiles?id=eq.{zero}", {"pontos_total": 999999})
    assert status in NEGADO and corpo["code"] == "42501", (status, corpo)

    for tabela in ("descartes", "profiles"):
        status, corpo = supabase_rest("GET", f"{tabela}?select=*")
        assert status in NEGADO, (tabela, status, corpo)

    for nome, args in (("meu_resumo", {}), ("registrar_descarte", {
            "p_ponto_id": ponto["id"], "p_tipo_id": pilhas, "p_quantidade": 1,
            "p_lat": ponto["latitude"], "p_lng": ponto["longitude"]})):
        status, corpo = supabase_rest("POST", f"rpc/{nome}", args)
        assert status in NEGADO, (nome, status, corpo)  # sem login: nem executa


def test_tipos_residuo_sao_publicos_e_iguais_aos_filtros(tipos):
    assert sorted(tipos) == sorted([
        "Celulares", "Pilhas e baterias", "Cabos e carregadores", "Computadores e periféricos", "Eletrodomésticos pequenos"])
    assert {n: t["pontos"] for n, t in tipos.items()} == {
        "Pilhas e baterias": 5, "Cabos e carregadores": 5, "Celulares": 20,
        "Computadores e periféricos": 50, "Eletrodomésticos pequenos": 30}
    assert all(t["fonte"] for t in tipos.values())


# ---------------------------------------------------------------------
# Usuário logado: só o próprio perfil, nunca os pontos
# ---------------------------------------------------------------------
def test_usuario_nao_altera_pontos_nem_escreve_em_descartes(ana, ponto, tipos):
    status, corpo = ana.rest("PATCH", f"profiles?id=eq.{ana.id}", {"pontos_total": 999999})
    assert status in NEGADO and corpo["code"] == "42501", (status, corpo)

    for coluna in ("id", "criado_em"):
        status, corpo = ana.rest("PATCH", f"profiles?id=eq.{ana.id}", {coluna: "2000-01-01T00:00:00Z" if coluna == "criado_em" else ana.id})
        assert status in NEGADO, (coluna, status, corpo)

    status, corpo = ana.rest("POST", "descartes", {
        "user_id": ana.id, "ponto_id": ponto["id"], "tipo_id": tipos["Celulares"]["id"],
        "quantidade": 1, "pontos": 999, "peso_kg_estimado": 1})
    assert status in NEGADO and corpo["code"] == "42501", (status, corpo)

    for metodo, caminho, corpo_ in (("PATCH", f"descartes?user_id=eq.{ana.id}", {"pontos": 999}), ("DELETE", f"descartes?user_id=eq.{ana.id}", None),
                                    ("POST", "profiles", {"id": ana.id, "apelido": "outro_apelido"}), ("DELETE", f"profiles?id=eq.{ana.id}", None)):
        status, corpo = ana.rest(metodo, caminho, corpo_)
        assert status in NEGADO, (metodo, caminho, status, corpo)

    _, perfil = ana.rest("GET", f"profiles?id=eq.{ana.id}&select=pontos_total")
    assert perfil == [{"pontos_total": 0}]


def test_usuario_altera_apelido_e_cidade_mas_nao_para_valor_invalido(ana):
    novo = _apelido("ana") + "b"
    status, corpo = ana.rest("PATCH", f"profiles?id=eq.{ana.id}", {"cidade": "Votorantim", "apelido": novo}, prefer="return=representation")
    assert status == 200 and corpo[0]["cidade"] == "Votorantim" and corpo[0]["apelido"] == novo, (status, corpo)
    ana.apelido = novo

    for invalido in ("ab", "tem espaco", "x" * 21, "açaí_ok"):
        status, corpo = ana.rest("PATCH", f"profiles?id=eq.{ana.id}", {"apelido": invalido})
        assert status == 400 and corpo["code"] == "23514", (invalido, status, corpo)


def test_usuario_nao_le_nem_altera_dados_de_outro(ana, beto, ponto, tipos):
    status, corpo = descartar(ana, ponto, tipos["Pilhas e baterias"]["id"], 2)
    assert status == 200, corpo

    # Ana vê só a si mesma
    _, perfis = ana.rest("GET", "profiles?select=id,apelido,pontos_total")
    assert [p["id"] for p in perfis] == [ana.id] and perfis[0]["pontos_total"] == 10
    _, regs = ana.rest("GET", "descartes?select=user_id")
    assert regs and {r["user_id"] for r in regs} == {ana.id}

    # Beto não vê nada da Ana, nem filtrando pelo id dela
    _, perfis_b = beto.rest("GET", "profiles?select=id,apelido")
    assert [p["id"] for p in perfis_b] == [beto.id]
    assert beto.rest("GET", f"profiles?id=eq.{ana.id}")[1] == []
    assert beto.rest("GET", "descartes?select=*")[1] == []
    assert beto.rest("GET", f"descartes?user_id=eq.{ana.id}")[1] == []

    # Beto tenta alterar o perfil da Ana: nenhuma linha é afetada
    status, corpo = beto.rest("PATCH", f"profiles?id=eq.{ana.id}", {"apelido": "invadida_" + RODADA}, prefer="return=representation")
    assert status == 200 and corpo == [], (status, corpo)
    assert ana.rest("GET", f"profiles?id=eq.{ana.id}&select=apelido")[1] == [{"apelido": ana.apelido}]

    # O resumo de cada um é só dele
    assert beto.rpc("meu_resumo")[1]["pontos_total"] == 0
    assert ana.rpc("meu_resumo")[1]["pontos_total"] == 10


# ---------------------------------------------------------------------
# registrar_descarte
# ---------------------------------------------------------------------
def test_registro_valido_calcula_pontos_no_banco(ana, ponto, tipos):
    pesos = tipos["Celulares"]["peso_estimado_kg"]
    status, corpo = descartar(ana, ponto, tipos["Celulares"]["id"], 3, dlat=0.0, dlng=0.0)  # exatamente no ponto
    assert status == 200, corpo
    assert corpo["pontos_ganhos"] == 60            # 20 × 3, vindo de tipos_residuo
    assert corpo["pontos_total"] == 70             # 10 do teste anterior + 60
    assert corpo["nivel"] == "Broto"               # 50–149
    assert float(corpo["peso_kg_estimado"]) == pytest.approx(float(pesos) * 3)

    resumo = ana.rpc("meu_resumo")[1]
    assert resumo["pontos_total"] == 70 and resumo["nivel"] == "Broto"
    assert resumo["descartes"] == 2 and resumo["itens"] == 5
    assert resumo["kg_estimados"] == pytest.approx(0.025 * 2 + float(pesos) * 3)

    # Não guarda onde o usuário estava
    _, linhas = ana.rest("GET", "descartes?select=*&limit=1")
    colunas = set(linhas[0])
    assert colunas == {"id", "user_id", "ponto_id", "tipo_id", "quantidade", "pontos", "peso_kg_estimado", "criado_em"}, colunas


@pytest.mark.parametrize("dlat,dlng,rotulo", [
    (FORA, 0.0, "a ~211 m ao norte"),
    (0.0, 0.0025, "a ~256 m a leste"),  # 0,0025° de longitude ≈ 256 m na latitude de Sorocaba
    (0.05, 0.05, "a ~7 km"),
])
def test_recusa_ponto_a_mais_de_200_m(ana, ponto, tipos, dlat, dlng, rotulo):
    status, corpo = descartar(ana, ponto, tipos["Pilhas e baterias"]["id"], 1, dlat=dlat, dlng=dlng)
    assert status == 400 and hint(corpo) == "longe_do_ponto", (rotulo, status, corpo)


def test_recusa_outra_cidade(ana, ponto, tipos):
    status, corpo = descartar(ana, ponto, tipos["Pilhas e baterias"]["id"], 1, lat=-23.5505, lng=-46.6333)  # São Paulo
    assert status == 400 and hint(corpo) == "longe_do_ponto", corpo


def test_aceita_dentro_dos_200_m(ana, ponto, tipos):
    status, corpo = descartar(ana, ponto, tipos["Pilhas e baterias"]["id"], 1, dlat=DENTRO, dlng=0.0005)
    assert status == 200, corpo


@pytest.mark.parametrize("quantidade", [0, 11, -1, 100, None])
def test_recusa_quantidade_invalida(ana, ponto, tipos, quantidade):
    status, corpo = descartar(ana, ponto, tipos["Pilhas e baterias"]["id"], quantidade)
    assert status == 400 and hint(corpo) == "quantidade_invalida", (quantidade, status, corpo)


def test_recusa_ponto_tipo_e_coordenadas_invalidos(ana, ponto, tipos):
    pilhas = tipos["Pilhas e baterias"]["id"]
    status, corpo = ana.rpc("registrar_descarte", {"p_ponto_id": "00000000-0000-0000-0000-000000000000", "p_tipo_id": pilhas,
                                                    "p_quantidade": 1, "p_lat": ponto["latitude"], "p_lng": ponto["longitude"]})
    assert status == 400 and hint(corpo) == "ponto_inexistente", corpo
    status, corpo = ana.rpc("registrar_descarte", {"p_ponto_id": ponto["id"], "p_tipo_id": 9999, "p_quantidade": 1,
                                                    "p_lat": ponto["latitude"], "p_lng": ponto["longitude"]})
    assert status == 400 and hint(corpo) == "tipo_inexistente", corpo
    for lat, lng in ((None, ponto["longitude"]), (95, ponto["longitude"]), (ponto["latitude"], 200)):
        status, corpo = ana.rpc("registrar_descarte", {"p_ponto_id": ponto["id"], "p_tipo_id": pilhas, "p_quantidade": 1,
                                                        "p_lat": lat, "p_lng": lng})
        assert status == 400 and hint(corpo) == "coordenadas_invalidas", (lat, lng, corpo)


def test_cliente_nao_consegue_informar_pontos_nem_peso(ana, ponto, tipos):
    # A função não tem parâmetros de pontos/peso: o PostgREST recusa argumentos que ela não conhece.
    status, corpo = ana.rpc("registrar_descarte", {
        "p_ponto_id": ponto["id"], "p_tipo_id": tipos["Pilhas e baterias"]["id"], "p_quantidade": 1,
        "p_lat": ponto["latitude"], "p_lng": ponto["longitude"], "p_pontos": 9999})
    assert status in (400, 404), (status, corpo)
    assert ana.rpc("meu_resumo")[1]["pontos_total"] < 9999


def test_sexto_registro_do_dia_e_recusado(ponto, tipos):
    carla = Usuario("carla")
    pilhas = tipos["Pilhas e baterias"]["id"]
    for i in range(5):
        status, corpo = descartar(carla, ponto, pilhas, 1)
        assert status == 200, (i + 1, corpo)
    status, corpo = descartar(carla, ponto, pilhas, 1)
    assert status == 400 and hint(corpo) == "limite_registros", corpo
    assert carla.rpc("meu_resumo")[1] == {"pontos_total": 25, "nivel": "Semente", "descartes": 5, "itens": 5, "kg_estimados": pytest.approx(0.125)}


def test_mais_de_30_itens_no_dia_e_recusado(ponto, tipos):
    davi = Usuario("davi")
    cabos = tipos["Cabos e carregadores"]["id"]
    for _ in range(2):  # 20 itens
        assert descartar(davi, ponto, cabos, 10)[0] == 200
    assert davi.rpc("meu_resumo")[1]["itens"] == 20
    status, corpo = descartar(davi, ponto, cabos, 10)  # 30 itens: limite exato, passa
    assert status == 200, corpo
    status, corpo = descartar(davi, ponto, cabos, 1)   # 31º item
    assert status == 400 and hint(corpo) == "limite_itens", corpo
    assert davi.rpc("meu_resumo")[1]["itens"] == 30


def test_limite_de_itens_recusa_antes_de_chegar_a_30(ponto, tipos):
    eva = Usuario("eva")
    cabos = tipos["Cabos e carregadores"]["id"]
    for _ in range(2):
        assert descartar(eva, ponto, cabos, 10)[0] == 200
    assert descartar(eva, ponto, cabos, 8)[0] == 200  # 28 itens
    status, corpo = descartar(eva, ponto, cabos, 3)   # 31 → recusa e NÃO soma nada
    assert status == 400 and hint(corpo) == "limite_itens", corpo
    assert eva.rpc("meu_resumo")[1]["itens"] == 28


# ---------------------------------------------------------------------
# Cadastro (trigger)
# ---------------------------------------------------------------------
@pytest.mark.parametrize("apelido", ["ab", "tem espaco", "x" * 21, "açaí_legal", "com-hifen", "", "a@b.c"])
def test_cadastro_com_apelido_invalido_e_recusado(apelido):
    suf = "inv" + secrets.token_hex(2)
    email, status, corpo = cadastrar_via_api(suf, apelido=apelido)
    assert status >= 400, (apelido, status, corpo)
    assert "access_token" not in (corpo if isinstance(corpo, dict) else {})
    # a conta não ficou criada
    assert entrar_via_api(email)[0] >= 400


def test_cadastro_sem_apelido_e_recusado():
    email = f"teste-ecotroca-{RODADA}-sem@{DOMINIO}"
    EMAILS_CRIADOS.append(email)
    status, corpo = supabase_rest("POST", "signup", {"email": email, "password": SENHA}, base="auth/v1")
    assert status >= 400, (status, corpo)


def test_cadastro_com_apelido_repetido_e_recusado(ana):
    # mesmo apelido da Ana, só com maiúsculas trocadas
    suf = "dup" + secrets.token_hex(2)
    email, status, corpo = cadastrar_via_api(suf, apelido=ana.apelido.upper())
    assert status >= 400, (status, corpo)
    assert entrar_via_api(email)[0] >= 400


def test_cadastro_valido_cria_perfil_com_padroes():
    u = Usuario("padrao" + secrets.token_hex(1))
    _, perfil = u.rest("GET", "profiles?select=apelido,cidade,pontos_total,criado_em")
    assert len(perfil) == 1
    assert perfil[0]["apelido"] == u.apelido and perfil[0]["cidade"] == "Sorocaba" and perfil[0]["pontos_total"] == 0
    # e o login com a senha funciona
    status, corpo = entrar_via_api(u.email)
    assert status == 200 and corpo["access_token"]


def teardown_module(module):
    print("\n[usuários de teste criados nesta rodada — remova-os]\n  "
          "delete from auth.users where email like 'teste-ecotroca-%@example.com';\n  "
          f"({len(EMAILS_CRIADOS)} e-mails usados)")

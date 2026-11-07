"""
Ranking: interface e contrato com o banco (Google Maps bloqueado).

Parte 1 — interface, com o RPC `ranking` simulado por um "banco falso" que repete as regras do
supabase/06-ranking.sql (roda sempre, mesmo antes de o SQL ser aplicado).
Parte 2 — contra o banco real do projeto; é PULADA enquanto supabase/06-ranking.sql não estiver
aplicado. Cria usuários reais `teste-ecotroca-*@example.com` (limpeza em test_11_pontos_banco.py).
A lógica do SQL em si (períodos, empate, limite, permissões) está em test_14_ranking_sql_local.py.
"""

import json
import re

import pytest

from conftest import esperar_lista, supabase_rest
from test_07_layout import ALVOS_PEQUENOS
from test_10_desempenho_a11y import AXE
from test_11_pontos_banco import Usuario, RODADA, SENHA
from test_13_interface_conta import abrir_conta, entrar_pela_interface, logar, posicao

LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]


# ---------------------------------------------------------------------
# Banco falso: as mesmas regras do SQL, em Python
# ---------------------------------------------------------------------
def pessoas_base():
    """14 pessoas: 12 pontuaram na semana, 3 no mês, todas no geral. Cada terceira mora em Votorantim."""
    pessoas = []
    for i in range(14):
        pessoas.append({
            "apelido": f"pessoa_{i + 1:02d}",
            "cidade": "Votorantim" if i % 3 == 2 else "Sorocaba",
            "pontos": {"semana": 200 - 10 * i if i < 12 else 0, "mes": 300 - 10 * i if i < 3 else 0, "geral": 1000 - 20 * i},
        })
    return pessoas


class BancoFalso:
    def __init__(self, pessoas=None):
        self.pessoas = pessoas if pessoas is not None else pessoas_base()
        self.chamadas = []  # [(nome, argumentos)]
        self.falhar = False

    def linhas(self, periodo, cidade):
        alvo = (cidade or "").strip().lower()
        achadas = [p for p in self.pessoas if p["pontos"][periodo] > 0 and (not alvo or p["cidade"].lower() == alvo)]
        achadas.sort(key=lambda p: (-p["pontos"][periodo], p["apelido"].lower()))
        return [{"posicao": i + 1, "apelido": p["apelido"], "cidade": p["cidade"], "pontos": p["pontos"][periodo]}
                for i, p in enumerate(achadas)]

    def responder(self, route):
        cors = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, OPTIONS"}
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=cors)
        nome = req.url.rstrip("/").rsplit("/", 1)[-1]
        args = req.post_data_json or {}
        self.chamadas.append((nome, args))
        if self.falhar:
            return route.fulfill(status=500, headers={**cors, "content-type": "application/json"}, body=json.dumps({"message": "falha simulada"}))
        todas = self.linhas(args["p_periodo"], args.get("p_cidade"))
        if nome == "ranking":
            corpo = todas[: min(max(args.get("p_limite") or 10, 1), 50)]
        else:  # minha_posicao
            auth = req.headers.get("authorization", "")
            corpo = [] if "eyJ" not in auth else self.minha(todas)
        route.fulfill(status=200, headers={**cors, "content-type": "application/json"}, body=json.dumps(corpo))

    minha_apelido = None

    def minha(self, todas):
        for l in todas:
            if l["apelido"] == self.minha_apelido:
                return [{"posicao": l["posicao"], "pontos": l["pontos"]}]
        return []

    def preparar(self, page):
        page.route("**/rest/v1/rpc/ranking", self.responder)
        page.route("**/rest/v1/rpc/minha_posicao", self.responder)

    def chamadas_de(self, nome):
        return [a for n, a in self.chamadas if n == nome]


def axe_do_ranking(page):
    page.add_script_tag(url=AXE)
    return page.evaluate(
        """async () => (await axe.run({ include: [['#ranking']] },
              { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }))
           .violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)"""
    )


def esperar_ranking(page):
    """O ranking terminou de carregar (com dados, vazio ou erro)."""
    page.wait_for_function("document.querySelector('#ranking-lista').getAttribute('aria-busy') === 'false'", timeout=20000)


def abrir_ranking(abrir, banco, largura=1280, altura=900, **kw):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900, preparar=banco.preparar, **kw)
    esperar_lista(p.page)
    esperar_ranking(p.page)
    return p


def linhas(page):
    return page.locator("#ranking-lista .rank")


def clicar_filtro(page, texto):
    botao = page.locator("#ranking .filtro", has_text=re.compile(f"^{texto}$"))
    botao.click()
    assert botao.get_attribute("aria-pressed") == "true"
    page.wait_for_function("document.querySelector('#ranking-lista').getAttribute('aria-busy') === 'false'")


# ---------------------------------------------------------------------
# Parte 1 — interface
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_top_10_destaques_filtros_e_contagem(abrir, largura, altura):
    banco = BancoFalso()
    p = abrir_ranking(abrir, banco, largura, altura)
    page = p.page

    # Semana (padrão): top 10 de 12 pessoas
    assert linhas(page).count() == 10
    primeiro = linhas(page).first
    assert primeiro.locator(".rank__pos").inner_text() == "1º"
    assert primeiro.locator(".rank__nome").inner_text() == "pessoa_01"
    assert primeiro.locator(".rank__cidade").inner_text() == "Sorocaba"
    assert primeiro.locator(".rank__pontos").inner_text() == "200 pontos"
    assert linhas(page).nth(9).locator(".rank__pos").inner_text() == "10º"
    assert page.locator("#ranking-contagem").inner_text() == "As 10 primeiras posições nesta semana."
    assert page.locator("#ranking-contagem").get_attribute("aria-live") == "polite"
    assert page.locator("#ranking-lista").get_attribute("aria-busy") == "false"
    assert banco.chamadas_de("ranking")[0] == {"p_periodo": "semana", "p_cidade": None, "p_limite": 10}

    # Anônimo: nada de "Minha cidade" nem de posição pessoal
    assert page.locator('[data-cidade="minha"]').is_hidden()
    assert page.locator("#ranking-minha").is_hidden()
    assert banco.chamadas_de("minha_posicao") == []

    # 1º, 2º e 3º em destaque só por tipografia e cor; sem caixas, sombras nem raio
    classes = [linhas(page).nth(i).get_attribute("class") for i in range(5)]
    assert classes[:3] == ["rank rank--1", "rank rank--2", "rank rank--3"] and classes[3:] == ["rank", "rank"]
    tam = lambda i: page.evaluate("i => parseFloat(getComputedStyle(document.querySelectorAll('#ranking-lista .rank__nome')[i]).fontSize)", i)
    assert tam(0) > tam(1) >= tam(2) > tam(3)
    cor = lambda i: page.evaluate("i => getComputedStyle(document.querySelectorAll('#ranking-lista .rank__pos')[i]).color", i)
    assert cor(0) != cor(3) and cor(1) != cor(3)
    estilo = page.evaluate("() => { const s = getComputedStyle(document.querySelector('#ranking-lista .rank')); return [s.boxShadow, s.borderRadius, s.borderTopWidth, s.backgroundColor]; }")
    assert estilo == ["none", "0px", "0px", "rgba(0, 0, 0, 0)"]

    # Mês: 3 pessoas
    clicar_filtro(page, "Mês")
    assert linhas(page).count() == 3
    assert page.locator("#ranking-contagem").inner_text() == "3 pessoas pontuaram neste mês."
    assert page.locator('#ranking [data-periodo="semana"]').get_attribute("aria-pressed") == "false"
    assert banco.chamadas_de("ranking")[-1]["p_periodo"] == "mes"

    # Geral: 14 pessoas, mostra 10
    clicar_filtro(page, "Geral")
    assert linhas(page).count() == 10
    assert page.locator("#ranking-contagem").inner_text() == "As 10 primeiras posições no geral."
    assert banco.chamadas_de("ranking")[-1]["p_periodo"] == "geral"

    clicar_filtro(page, "Semana")
    assert linhas(page).first.locator(".rank__nome").inner_text() == "pessoa_01"
    assert p.erros == [], p.erros


def test_estado_vazio_acolhedor(abrir):
    banco = BancoFalso(pessoas=[])
    p = abrir_ranking(abrir, banco)
    page = p.page
    assert linhas(page).count() == 0
    assert page.locator("#ranking-lista .lista__estado").inner_text() == "Ninguém pontuou ainda neste período."
    assert page.locator("#ranking-contagem").inner_text() == "Nenhuma pessoa no ranking nesta semana."
    clicar_filtro(page, "Geral")
    assert page.locator("#ranking-lista .lista__estado").inner_text() == "Ninguém pontuou ainda neste período."


def test_erro_de_carregamento_e_tentar_de_novo(abrir):
    banco = BancoFalso()
    banco.falhar = True
    p = abrir("/", largura=1280, altura=900, preparar=banco.preparar)
    page = p.page
    esperar_lista(page)
    estado = page.locator("#ranking-lista .lista__estado")
    estado.wait_for()
    page.wait_for_function("document.querySelector('#ranking-lista .lista__estado button')")
    assert "Não foi possível carregar o ranking agora." in estado.inner_text()
    banco.falhar = False
    page.click("#ranking-lista .lista__estado button")
    page.wait_for_selector("#ranking-lista .rank")
    assert linhas(page).count() == 10


def test_texto_do_banco_e_escapado(abrir):
    maldoso = '<img src=x onerror="window.__ranking=1">'
    banco = BancoFalso(pessoas=[{"apelido": maldoso, "cidade": "<b>Cidade</b>", "pontos": {"semana": 10, "mes": 10, "geral": 10}}])
    p = abrir_ranking(abrir, banco)
    page = p.page
    linha = linhas(page).first
    assert linha.locator(".rank__nome").inner_text() == maldoso
    assert linha.locator(".rank__cidade").inner_text() == "<b>Cidade</b>"
    assert page.locator("#ranking-lista img, #ranking-lista b").count() == 0
    assert page.evaluate("window.__ranking") is None


@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_acessibilidade_e_alvos_de_toque(abrir, largura, altura):
    p = abrir_ranking(abrir, BancoFalso(), largura, altura)
    page = p.page
    page.locator("#ranking").scroll_into_view_if_needed()
    assert axe_do_ranking(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []
    assert page.evaluate("[document.documentElement.scrollWidth, innerWidth]")[0] <= largura
    assert page.locator("#ranking").get_attribute("aria-labelledby") == "ranking-titulo"
    assert page.locator("#ranking .filtro").evaluate_all("bs => bs.every(b => b.hasAttribute('aria-pressed'))")
    assert p.erros == [], p.erros


def test_filtros_por_teclado_e_foco_visivel(abrir):
    p = abrir_ranking(abrir, BancoFalso())
    page = p.page
    botao = page.locator('#ranking [data-periodo="mes"]')
    botao.focus()
    assert page.evaluate("() => { const s = getComputedStyle(document.activeElement); return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2; }")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('#ranking-lista .rank').length === 3")
    assert botao.get_attribute("aria-pressed") == "true"


def test_menu_tem_link_para_o_ranking(abrir):
    p = abrir_ranking(abrir, BancoFalso(), 1280, 900)
    assert p.page.locator('#menu-principal a[href="#ranking"]').inner_text() == "Ranking"
    # a seção fica entre Mapa e Como funciona
    ordem = p.page.evaluate("[...document.querySelectorAll('main > section')].map(s => s.id)")
    assert ordem.index("mapa") < ordem.index("ranking") < ordem.index("como-funciona")


def test_logado_ve_minha_cidade_e_a_propria_posicao(abrir):
    usuario = Usuario("rkui")
    # Fora do top 10 no geral (13ª na semana), mas 9ª entre as pessoas de Sorocaba
    pessoas = pessoas_base() + [{"apelido": usuario.apelido, "cidade": "Sorocaba", "pontos": {"semana": 75, "mes": 0, "geral": 50}}]
    banco = BancoFalso(pessoas)
    banco.minha_apelido = usuario.apelido
    p = abrir_ranking(abrir, banco, 375, 812)
    page = p.page
    logar(page, usuario)

    # "Minha cidade" aparece e a posição pessoal fica separada, abaixo da lista
    page.wait_for_selector('#ranking [data-cidade="minha"]:not([hidden])', timeout=20000)
    page.locator("#ranking-minha:not([hidden])").wait_for(timeout=20000)
    assert page.locator("#ranking-minha .rank__rotulo").text_content() == "Sua posição"
    posicao_geral = [l for l in banco.linhas("semana", None) if l["apelido"] == usuario.apelido][0]["posicao"]
    assert posicao_geral > 10
    assert page.locator("#ranking-minha .rank__minha-linha").inner_text() == f"{posicao_geral}º, com 75 pontos"
    assert page.evaluate("document.querySelector('#ranking-minha').compareDocumentPosition(document.querySelector('#ranking-lista')) & Node.DOCUMENT_POSITION_PRECEDING")
    assert linhas(page).locator(".rank__voce").count() == 0
    assert banco.chamadas_de("minha_posicao")[-1] == {"p_periodo": "semana", "p_cidade": None}

    # Minha cidade: o filtro usa a cidade do perfil (Sorocaba) e a pessoa entra no top 10, destacada
    clicar_filtro(page, "Minha cidade")
    assert banco.chamadas_de("ranking")[-1] == {"p_periodo": "semana", "p_cidade": "Sorocaba", "p_limite": 10}
    assert page.locator("#ranking-contagem").inner_text() == "9 pessoas pontuaram nesta semana, em Sorocaba."
    assert set(page.locator("#ranking-lista .rank__cidade").all_text_contents()) == {"Sorocaba"}
    dela = page.locator("#ranking-lista .rank--voce")
    assert dela.count() == 1 and dela.locator(".rank__voce").text_content() == "Você"
    assert dela.locator(".rank__nome").inner_text().startswith(usuario.apelido)
    assert page.locator("#ranking-minha").is_hidden()  # dentro do top: sem bloco separado

    # No mês ela não pontuou
    clicar_filtro(page, "Mês")
    page.locator("#ranking-minha:not([hidden])").wait_for()
    assert page.locator("#ranking-minha").inner_text() == "Você ainda não pontuou neste período."

    # Sair: some "Minha cidade", o filtro volta para todas e some a posição pessoal
    menu_aberto = page.locator(".topo__menu")
    menu_aberto.click()
    page.click("[data-conta-sair]")
    page.wait_for_selector('#ranking [data-cidade="minha"]', state="hidden")
    assert page.locator('#ranking [data-cidade="todas"]').get_attribute("aria-pressed") == "true"
    page.wait_for_function("document.querySelector('#ranking-contagem').textContent.length > 0 && !document.querySelector('#ranking-contagem').textContent.includes('Sorocaba')")
    assert page.locator("#ranking-minha").is_hidden()
    assert p.erros == [], p.erros


def test_modo_demonstracao_esconde_o_ranking(abrir):
    def preparar(page):
        cfg = open("js/config.js", encoding="utf-8").read().replace("'https://uqgqyqehykkxlnrnoxml.supabase.co'", "'COLE_A_URL'")
        page.route("**/js/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=cfg))

    p = abrir("/", largura=1280, altura=900, preparar=preparar)
    esperar_lista(p.page)
    assert p.page.locator("#ranking").is_hidden()
    assert p.page.locator("[data-ranking-nav]").is_hidden()
    assert p.erros == [], p.erros


# ---------------------------------------------------------------------
# Parte 2 — contra o banco real (precisa do 06-ranking.sql aplicado)
# ---------------------------------------------------------------------
NEGADO = (401, 403)
DENTRO = 0.0005  # ~55 m


@pytest.fixture(scope="module")
def banco_com_ranking():
    status, corpo = supabase_rest("POST", "rpc/ranking", {"p_periodo": "geral", "p_cidade": None, "p_limite": 1})
    if status == 404 and isinstance(corpo, dict) and corpo.get("code") == "PGRST202":
        pytest.skip("O banco ainda não tem a função ranking: aplique supabase/06-ranking.sql no SQL Editor.")
    assert status == 200, (status, corpo)


@pytest.fixture(scope="module")
def cenario(banco_com_ranking, pontos_db):
    """Três pessoas com pontos diferentes, em duas cidades inventadas (para isolar de outros testes)."""
    ponto = pontos_db[0]
    tipos = {t["nome"]: t["id"] for t in supabase_rest("GET", "tipos_residuo?select=id,nome")[1]}
    cidade_x, cidade_y, cidade_vazia = f"CidadeX{RODADA}", f"CidadeY{RODADA}", f"Vazia{RODADA}"
    ana, beto, carla, davi = Usuario("rka"), Usuario("rkb"), Usuario("rkc"), Usuario("rkd")
    for usuario, cidade in ((ana, cidade_x), (carla, cidade_x), (beto, cidade_y), (davi, cidade_x)):
        status, corpo = usuario.rest("PATCH", f"profiles?id=eq.{usuario.id}", {"cidade": cidade}, prefer="return=representation")
        assert status == 200 and corpo[0]["cidade"] == cidade, corpo

    def registrar(usuario, tipo, quantidade):
        status, corpo = usuario.rpc("registrar_descarte", {
            "p_ponto_id": ponto["id"], "p_tipo_id": tipos[tipo], "p_quantidade": quantidade,
            "p_lat": ponto["latitude"] + DENTRO, "p_lng": ponto["longitude"]})
        assert status == 200, corpo

    registrar(ana, "Computadores e periféricos", 1)   # 50 pontos
    registrar(beto, "Celulares", 3)                   # 60 pontos
    registrar(carla, "Pilhas e baterias", 2)          # 10 pontos
    return {"ana": ana, "beto": beto, "carla": carla, "davi": davi, "x": cidade_x, "y": cidade_y, "vazia": cidade_vazia}


def rpc_anonimo(nome, args):
    return supabase_rest("POST", f"rpc/{nome}", args)


def top(cidade, periodo="geral", limite=10):
    status, corpo = rpc_anonimo("ranking", {"p_periodo": periodo, "p_cidade": cidade, "p_limite": limite})
    assert status == 200, corpo
    return corpo


def test_banco_ordem_e_filtro_de_cidade(cenario):
    ana, carla = cenario["ana"], cenario["carla"]
    assert top(cenario["x"]) == [
        {"posicao": 1, "apelido": ana.apelido, "cidade": cenario["x"], "pontos": 50},
        {"posicao": 2, "apelido": carla.apelido, "cidade": cenario["x"], "pontos": 10}]
    assert top(cenario["y"]) == [{"posicao": 1, "apelido": cenario["beto"].apelido, "cidade": cenario["y"], "pontos": 60}]
    # Sem filtro de cidade, o Beto (60) vem antes da Ana (50), que vem antes da Carla (10)
    geral = [l["apelido"] for l in top(None, "geral", 50)]
    assert geral.index(cenario["beto"].apelido) < geral.index(ana.apelido) < geral.index(carla.apelido)


def test_banco_periodos_e_estado_vazio(cenario):
    for periodo in ("semana", "mes", "geral"):  # acabaram de pontuar: entram em todos
        assert [l["apelido"] for l in top(cenario["x"], periodo)] == [cenario["ana"].apelido, cenario["carla"].apelido]
    assert top(cenario["vazia"]) == []          # estado vazio
    assert cenario["davi"].apelido not in [l["apelido"] for l in top(cenario["x"])]  # nunca pontuou


def test_banco_limite_e_periodo_invalido(cenario):
    assert len(top(cenario["x"], limite=1)) == 1
    for invalido in (0, -3, None):
        assert len(top(cenario["x"], limite=invalido)) == 2  # volta ao padrão de 10
    assert len(top(None, limite=9999)) <= 50
    status, corpo = rpc_anonimo("ranking", {"p_periodo": "ano", "p_cidade": None, "p_limite": 5})
    assert status == 400 and corpo.get("hint") == "periodo_invalido", corpo


def test_banco_anonimo_chama_ranking_mas_nao_le_tabelas_nem_minha_posicao(cenario):
    linha = top(cenario["x"])[0]
    assert set(linha) == {"posicao", "apelido", "cidade", "pontos"}   # nada de id, e-mail ou descarte
    for tabela in ("descartes", "profiles"):
        status, corpo = supabase_rest("GET", f"{tabela}?select=*")
        assert status in NEGADO and corpo["code"] == "42501", (tabela, status, corpo)
    status, corpo = rpc_anonimo("minha_posicao", {"p_periodo": "geral", "p_cidade": None})
    assert status in NEGADO and corpo["code"] == "42501", (status, corpo)
    status, corpo = rpc_anonimo("ranking_linhas", {"p_periodo": "geral", "p_cidade": None})
    assert status in NEGADO or status == 404, (status, corpo)  # auxiliar interna: não é exposta


def test_banco_minha_posicao(cenario):
    ana, carla, beto, davi = cenario["ana"], cenario["carla"], cenario["beto"], cenario["davi"]
    args = {"p_periodo": "geral", "p_cidade": cenario["x"]}
    assert ana.rpc("minha_posicao", args) == (200, [{"posicao": 1, "pontos": 50}])
    assert carla.rpc("minha_posicao", args) == (200, [{"posicao": 2, "pontos": 10}])
    assert davi.rpc("minha_posicao", args) == (200, [])    # não pontuou
    assert beto.rpc("minha_posicao", args) == (200, [])    # fora do filtro de cidade
    assert beto.rpc("minha_posicao", {"p_periodo": "geral", "p_cidade": cenario["y"]}) == (200, [{"posicao": 1, "pontos": 60}])
    status, corpo = ana.rpc("minha_posicao", {"p_periodo": "ano", "p_cidade": None})
    assert status == 400 and corpo.get("hint") == "periodo_invalido"
    # logado também lê o ranking público
    assert ana.rpc("ranking", {"p_periodo": "geral", "p_cidade": cenario["x"], "p_limite": 10})[0] == 200


@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_banco_interface_com_dados_reais(abrir, cenario, largura, altura):
    ana = cenario["ana"]
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900, ranking_real=True)
    page = p.page
    esperar_lista(page)
    esperar_ranking(page)

    logar(page, ana)
    page.wait_for_selector('#ranking [data-cidade="minha"]:not([hidden])', timeout=20000)
    clicar_filtro(page, "Minha cidade")
    page.wait_for_function("document.querySelectorAll('#ranking-lista .rank').length === 2")
    nomes = page.locator("#ranking-lista .rank__nome").all_text_contents()
    assert nomes[0].startswith(ana.apelido) and "Você" in nomes[0]
    assert nomes[1] == cenario["carla"].apelido
    assert page.locator("#ranking-lista .rank__pontos").all_text_contents() == ["50 pontos", "10 pontos"]
    assert page.locator("#ranking-contagem").inner_text() == f"2 pessoas pontuaram nesta semana, em {cenario['x']}."
    assert axe_do_ranking(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

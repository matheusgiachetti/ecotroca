"""
Medalhas e "Como os pontos funcionam" (Google Maps bloqueado).

Parte 1 — interface, com os RPCs `registrar_descarte`, `minhas_medalhas` e `regras_pontos` simulados
(roda sempre, mesmo antes de o supabase/07-medalhas.sql ser aplicado). O login é real: cria usuários
`teste-ecotroca-*@example.com` (limpeza em test_11_pontos_banco.py). Nenhum descarte real é gravado.
Parte 2 — contra o banco real; é PULADA enquanto supabase/07-medalhas.sql não estiver aplicado.
A lógica do SQL (condições das medalhas, RLS, regras) está em test_15_medalhas_sql_local.py.
"""

import copy
import json
import re

import pytest

from conftest import MEDALHAS_PADRAO, REGRAS_PADRAO, esperar_lista, responder_rpc, supabase_rest
from test_07_layout import ALVOS_PEQUENOS
from test_10_desempenho_a11y import AXE
from test_11_pontos_banco import Usuario
from test_13_interface_conta import abrir_cartao, axe_do_painel, esperar_localizacao_automatica, logar, menu_aberto, posicao

LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]
PRIMEIRO, DEZ, TRES, CEM = "Primeiro descarte", "10 itens descartados", "3 tipos de resíduo", "100 pontos"
CODIGOS = {PRIMEIRO: "primeiro_descarte", DEZ: "dez_itens", TRES: "tres_tipos", CEM: "cem_pontos"}
NEGADO = (401, 403)
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, OPTIONS"}


# ---------------------------------------------------------------------
# Banco falso: só o que muda neste teste (descarte com medalhas e a lista de medalhas)
# ---------------------------------------------------------------------
class BancoDeMedalhas:
    def __init__(self, fila):
        self.fila = list(fila)          # medalhas_novas de cada registro, na ordem
        self.conquistadas = []          # nomes
        self.registros = []             # argumentos recebidos
        self.pontos = 0

    def registrar(self, route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        args = route.request.post_data_json
        self.registros.append(args)
        novas = self.fila.pop(0) if self.fila else []
        self.conquistadas += novas
        self.pontos += 20 * args["p_quantidade"]
        corpo = {"descarte_id": "00000000-0000-0000-0000-000000000001", "pontos_ganhos": 20 * args["p_quantidade"],
                 "pontos_total": self.pontos, "nivel": "Semente", "peso_kg_estimado": 0.17 * args["p_quantidade"],
                 "medalhas_novas": novas}
        route.fulfill(status=200, headers={**CORS, "content-type": "application/json"}, body=json.dumps(corpo))

    def medalhas(self, route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        corpo = [{**m, "conquistada": m["nome"] in self.conquistadas,
                  "conquistada_em": "2026-11-07T15:30:00+00:00" if m["nome"] in self.conquistadas else None}
                 for m in MEDALHAS_PADRAO]
        route.fulfill(status=200, headers={**CORS, "content-type": "application/json"}, body=json.dumps(corpo))

    def preparar(self, page):
        page.route("**/rest/v1/rpc/registrar_descarte", self.registrar)
        page.route("**/rest/v1/rpc/minhas_medalhas", self.medalhas)


def registrar_pela_interface(page, ponto, tipo="Celulares", quantidade="1", primeiro=True):
    if primeiro:
        abrir_cartao(page, ponto).click()
        page.wait_for_selector("#painel-descarte[open]")
    else:
        page.click("#descarte-outro")
    page.wait_for_selector("#descarte-tipos .opcao")
    page.locator("#descarte-tipos .opcao", has_text=tipo).click()
    page.fill("#descarte-quantidade", quantidade)
    page.click("#descarte-confirmar")
    page.wait_for_selector("#descarte-resultado", state="visible", timeout=20000)


def axe_da_secao(page, seletor):
    page.add_script_tag(url=AXE)
    return page.evaluate(
        """async (seletor) => (await axe.run({ include: [[seletor]] },
              { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }))
           .violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)""",
        seletor,
    )


# ---------------------------------------------------------------------
# Parte 1 — interface
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_aviso_de_medalha_e_secao_de_medalhas(abrir, pontos_db, largura, altura):
    ponto = pontos_db[0]
    usuario = Usuario(f"mdl{largura}")
    banco = BancoDeMedalhas([[PRIMEIRO], [DEZ, CEM]])
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900, geo=posicao(ponto, 0.0005), permitir_geo=True,
              preparar=banco.preparar)
    page = p.page
    esperar_lista(page)
    esperar_localizacao_automatica(page)
    logar(page, usuario)

    # 1º registro: um aviso de medalha, no resultado e anunciado
    registrar_pela_interface(page, ponto)
    assert banco.registros[0]["p_quantidade"] == 1
    aviso = page.locator("#descarte-resultado-medalha")
    assert aviso.is_visible() and aviso.inner_text() == f"Nova medalha: {PRIMEIRO}."
    assert f"Nova medalha: {PRIMEIRO}." in page.locator("#anuncio").inner_text()
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

    # 2º registro: duas medalhas de uma vez, em português correto
    registrar_pela_interface(page, ponto, "Celulares", "2", primeiro=False)
    assert aviso.inner_text() == f"Novas medalhas: {DEZ} e {CEM}."
    assert "Novas medalhas" in page.locator("#anuncio").inner_text()
    page.click("#descarte-resultado [data-fechar]")

    # Um registro sem medalha nova não mostra aviso
    registrar_pela_interface(page, ponto)  # a fila de medalhas acabou: nada novo
    assert page.locator("#descarte-resultado-texto").is_visible() and aviso.is_hidden()
    page.click("#descarte-resultado [data-fechar]")

    # Minha conta: conquistadas em destaque, bloqueadas apagadas
    abrir_conta_com_medalhas(page)
    itens = page.locator("#resumo-medalhas .medalha")
    assert itens.count() == 4
    ganhas = page.locator("#resumo-medalhas .medalha--ganha .medalha__nome").all_text_contents()
    bloqueadas = page.locator("#resumo-medalhas .medalha--bloqueada .medalha__nome").all_text_contents()
    assert ganhas == [PRIMEIRO, DEZ, CEM] and bloqueadas == [TRES]
    assert page.locator("#resumo-medalhas .medalha--ganha .medalha__estado").first.inner_text() == "Conquistada em 07/11/2026"
    assert page.locator("#resumo-medalhas .medalha--bloqueada .medalha__estado").inner_text() == "Ainda não conquistada"
    assert page.locator("#medalhas-resumo").inner_text() == "3 de 4 medalhas conquistadas."
    assert page.locator("#medalhas-resumo").get_attribute("aria-live") == "polite"
    cores = page.evaluate("""() => [document.querySelector('.medalha--ganha .medalha__nome'), document.querySelector('.medalha--bloqueada .medalha__nome')]
                             .map(e => getComputedStyle(e).color)""")
    assert cores[0] != cores[1]
    # lista tipográfica: sem caixa, contorno nem sombra
    caixa = page.evaluate("""() => { const e = getComputedStyle(document.querySelector('.medalha'));
                                    return [e.boxShadow, e.borderRadius, e.borderLeftWidth, e.backgroundColor]; }""")
    assert caixa[0] == "none" and caixa[1] == "0px" and caixa[2] == "0px" and caixa[3] == "rgba(0, 0, 0, 0)"
    assert "Peso estimado: peso médio por item, por tipo de resíduo" in page.locator("#vista-conta").inner_text()
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []
    assert p.erros == [], p.erros


def abrir_conta_com_medalhas(page):
    menu_aberto(page)
    page.click("[data-conta-abrir]")
    page.wait_for_selector("#painel-conta[open]")
    page.wait_for_function("document.querySelector('#resumo-medalhas').getAttribute('aria-busy') === 'false'", timeout=20000)


def test_erro_ao_carregar_medalhas_tem_tentar_de_novo(abrir):
    usuario = Usuario("mdlerr")
    estado = {"falhar": True}

    def medalhas(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if estado["falhar"]:
            return route.fulfill(status=500, headers={**CORS, "content-type": "application/json"}, body=json.dumps({"message": "falha simulada"}))
        route.fulfill(status=200, headers={**CORS, "content-type": "application/json"}, body=json.dumps(MEDALHAS_PADRAO))

    p = abrir("/", largura=375, altura=812, toque=True, preparar=lambda page: page.route("**/rest/v1/rpc/minhas_medalhas", medalhas))
    page = p.page
    esperar_lista(page)
    logar(page, usuario)
    abrir_conta_com_medalhas(page)
    assert "Não foi possível carregar as suas medalhas" in page.locator("#medalhas-erro").inner_text()
    assert page.locator("#resumo-medalhas .medalha").count() == 0
    # o resto da conta continua funcionando
    page.wait_for_function("document.querySelector('#resumo-nivel').textContent === 'Semente'")
    estado["falhar"] = False
    page.click("#medalhas-tentar")
    page.wait_for_selector("#resumo-medalhas .medalha")
    assert page.locator("#medalhas-erro").inner_text() == "" and page.locator("#medalhas-tentar").is_hidden()
    assert page.locator("#resumo-medalhas .medalha").count() == 4


def regras_de_teste():
    r = copy.deepcopy(REGRAS_PADRAO)
    r["tipos"][2]["pontos"] = 77
    r.update(raio_m=321, max_registros=7, max_itens=33, quantidade_max=12)
    r["niveis"][1]["de"] = 80
    r["medalhas"][0] = {"nome": '<img src=x onerror="window.__xss=1">Medalha X', "descricao": "Texto <b>do banco</b>."}
    return r


@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_secao_como_os_pontos_funcionam_le_os_valores_do_banco(abrir, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900,
              preparar=lambda page: page.route("**/rest/v1/rpc/regras_pontos", responder_rpc(regras_de_teste())))
    page = p.page
    esperar_lista(page)
    page.wait_for_function("document.querySelector('#regras-corpo').getAttribute('aria-busy') === 'false'", timeout=20000)
    secao = page.locator("#pontos")
    assert secao.locator("h2").inner_text() == "Como os pontos funcionam"

    # pontos por tipo: o valor vem do banco
    linha = secao.locator(".regras__lista dt", has_text="Celulares").locator("xpath=..")
    assert linha.locator("dd").inner_text() == "77 pontos"
    assert secao.locator(".regras__lista dt").count() == 5
    # níveis a partir dos limites do banco (Broto começa em 80, então Semente vai até 79)
    texto_niveis = secao.locator(".regras__grupo", has=page.locator("h3", has_text="Níveis")).inner_text()
    assert "Semente" in texto_niveis and "de 0 a 79 pontos" in texto_niveis and "de 80 a 149 pontos" in texto_niveis
    assert "700 pontos ou mais" in texto_niveis
    # limites e raio
    limites = secao.locator(".regras__grupo", has=page.locator("h3", has_text="Regras e limites")).inner_text()
    for esperado in ("até 321 m", "de 1 a 12 itens", "No máximo 7 registros por dia.", "No máximo 33 itens por dia.", "horário de Brasília"):
        assert esperado in limites, esperado
    assert "peso médio por item, por tipo de resíduo" in limites
    # medalhas: texto do banco só como texto
    medalhas = secao.locator(".regras__grupo", has=page.locator("h3", has_text="Medalhas"))
    assert "Medalha X" in medalhas.inner_text() and "Texto <b>do banco</b>." in medalhas.inner_text()
    assert "Elas não dão pontos" in medalhas.inner_text()
    assert page.evaluate("window.__xss") is None and secao.locator("img, b").count() == 0
    # nenhuma equivalência ambiental (não há fator com fonte verificada)
    assert not re.search(r"CO2|CO₂|carbono|árvores? (salva|plantada)", secao.inner_text(), re.I)

    # menu e posição na página
    assert page.locator('#menu-principal a[href="#pontos"]').text_content() == "Pontos"
    ordem = page.evaluate("[...document.querySelectorAll('main > section')].map(s => s.id)")
    assert ordem.index("ranking") < ordem.index("pontos") < ordem.index("como-funciona")
    # sem cartões: lista sem sombra nem raio
    assert page.evaluate("getComputedStyle(document.querySelector('.regras__grupo')).boxShadow") == "none"
    assert axe_da_secao(page, "#pontos") == []
    assert page.evaluate(ALVOS_PEQUENOS) == []
    assert p.erros == [], p.erros


def test_regras_com_erro_tentam_de_novo(abrir):
    estado = {"falhar": True}

    def regras(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if estado["falhar"]:
            return route.fulfill(status=500, headers={**CORS, "content-type": "application/json"}, body=json.dumps({"message": "falha simulada"}))
        route.fulfill(status=200, headers={**CORS, "content-type": "application/json"}, body=json.dumps(REGRAS_PADRAO))

    p = abrir("/", largura=375, altura=812, toque=True, preparar=lambda page: page.route("**/rest/v1/rpc/regras_pontos", regras))
    page = p.page
    esperar_lista(page)
    page.wait_for_selector("#regras-corpo .botao")
    assert "Não foi possível carregar as regras" in page.locator("#regras-corpo").inner_text()
    assert page.locator("#regras-corpo [role=alert]").count() == 1
    estado["falhar"] = False
    page.click("#regras-corpo .botao")
    page.wait_for_selector("#regras-corpo .regras__grupo")
    assert page.locator("#regras-corpo .botao").count() == 0
    # o resto do site continua sem depender das regras
    assert page.locator("#lista-pontos .ponto").count() > 0


def test_modo_demonstracao_esconde_a_secao_de_regras(abrir):
    def preparar(page):
        cfg = open("js/config.js", encoding="utf-8").read().replace("'https://uqgqyqehykkxlnrnoxml.supabase.co'", "'COLE_A_URL'")
        page.route("**/js/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=cfg))

    p = abrir("/", largura=1280, altura=900, preparar=preparar)
    esperar_lista(p.page)
    assert p.page.locator("#pontos").is_hidden() and p.page.locator("[data-pontos-nav]").is_hidden()
    assert p.erros == [], p.erros


# ---------------------------------------------------------------------
# Parte 2 — contra o banco real (precisa do 07-medalhas.sql aplicado)
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def banco_com_medalhas():
    status, corpo = supabase_rest("POST", "rpc/regras_pontos", {})
    if status == 404 and isinstance(corpo, dict) and corpo.get("code") == "PGRST202":
        pytest.skip("O banco ainda não tem regras_pontos: aplique supabase/05 e 07 no SQL Editor.")
    assert status == 200, (status, corpo)
    return corpo


def test_banco_regras_pontos_bate_com_as_tabelas_e_e_publica(banco_com_medalhas):
    regras = banco_com_medalhas
    status, tipos = supabase_rest("GET", "tipos_residuo?select=nome,pontos&order=id")
    assert status == 200 and regras["tipos"] == tipos
    assert regras["raio_m"] == 200 and regras["max_registros"] == 5 and regras["max_itens"] == 30
    assert regras["fuso"] == "America/Sao_Paulo"
    assert [(n["nome"], n["de"]) for n in regras["niveis"]] == [("Semente", 0), ("Broto", 50), ("Muda", 150), ("Árvore", 350), ("Floresta", 700)]
    assert [m["nome"] for m in regras["medalhas"]] == [PRIMEIRO, DEZ, TRES, CEM]
    assert all(set(m) == {"nome", "descricao"} for m in regras["medalhas"])


def test_banco_anonimo_nao_le_medalhas(banco_com_medalhas):
    assert supabase_rest("POST", "rpc/minhas_medalhas", {})[0] in NEGADO
    assert supabase_rest("GET", "usuario_medalhas?select=*")[0] in NEGADO
    assert supabase_rest("GET", "medalhas?select=*")[0] in NEGADO
    assert supabase_rest("POST", "rpc/conceder_medalhas", {"p_uid": "00000000-0000-0000-0000-000000000000"})[0] in NEGADO + (404,)


def test_banco_ninguem_escreve_nem_chama_a_concessao(banco_com_medalhas):
    u = Usuario("mdlpermissao")
    status, corpo = u.rest("POST", "usuario_medalhas", {"user_id": u.id, "medalha_codigo": "cem_pontos"})
    assert status in NEGADO, (status, corpo)
    assert u.rest("DELETE", f"usuario_medalhas?user_id=eq.{u.id}")[0] in NEGADO
    assert u.rest("PATCH", "medalhas?codigo=eq.cem_pontos", {"nome": "x"})[0] in NEGADO
    status, corpo = u.rpc("conceder_medalhas", {"p_uid": u.id})
    assert status in NEGADO + (404,), (status, corpo)
    status, corpo = u.rpc("minhas_medalhas")
    assert status == 200 and [m["conquistada"] for m in corpo] == [False] * 4


def test_banco_ponta_a_ponta_pela_interface(abrir, pontos_db, banco_com_medalhas):
    """Descarte REAL (um usuário de teste): a medalha aparece no resultado e em Minha conta, sem mexer nos pontos."""
    ponto = pontos_db[0]
    usuario = Usuario("mdlreal")
    outro = Usuario("mdlreal2")
    p = abrir("/", largura=1280, altura=900, geo=posicao(ponto, 0.0005), permitir_geo=True, regras_reais=True, ranking_real=False)
    page = p.page
    esperar_lista(page)
    esperar_localizacao_automatica(page)
    logar(page, usuario)

    registrar_pela_interface(page, ponto, "Celulares", "2")  # 40 pontos
    assert page.locator("#descarte-resultado-medalha").inner_text() == f"Nova medalha: {PRIMEIRO}."
    registrar_pela_interface(page, ponto, "Pilhas e baterias", "8", primeiro=False)  # 10 itens no total, 40 pontos
    assert page.locator("#descarte-resultado-medalha").inner_text() == f"Nova medalha: {DEZ}."
    assert page.locator("#descarte-resultado-texto").inner_text() == "+40 pontos. Você agora tem 80 pontos, nível Broto."
    page.click("#descarte-resultado [data-fechar]")

    abrir_conta_com_medalhas(page)
    assert page.locator("#resumo-medalhas .medalha--ganha .medalha__nome").all_text_contents() == [PRIMEIRO, DEZ]
    assert page.locator("#medalhas-resumo").inner_text() == "2 de 4 medalhas conquistadas."
    assert page.locator("#resumo-barra").evaluate("b => [b.value, b.max]") == [30, 100]  # Broto: 80 de 50 a 150
    assert page.locator("#resumo-pontos").inner_text() == "80"  # medalha não dá pontos
    assert axe_do_painel(page) == []

    # O banco confirma, e a outra pessoa não vê nada disso
    status, corpo = usuario.rpc("minhas_medalhas")
    assert [m["codigo"] for m in corpo if m["conquistada"]] == ["primeiro_descarte", "dez_itens"]
    assert usuario.rpc("meu_resumo")[1]["pontos_total"] == 80
    assert [m["conquistada"] for m in outro.rpc("minhas_medalhas")[1]] == [False] * 4
    assert outro.rest("GET", f"usuario_medalhas?user_id=eq.{usuario.id}&select=*") == (200, [])
    assert p.erros == [], p.erros


def test_banco_secao_de_regras_mostra_os_valores_reais(abrir, banco_com_medalhas):
    regras = banco_com_medalhas
    p = abrir("/", largura=375, altura=812, toque=True, regras_reais=True)
    page = p.page
    esperar_lista(page)
    page.wait_for_selector("#regras-corpo .regras__grupo", timeout=20000)
    for t in regras["tipos"]:
        linha = page.locator("#pontos .regras__lista dt", has_text=re.compile(f"^{re.escape(t['nome'])}$")).locator("xpath=..")
        assert linha.locator("dd").inner_text() == f"{t['pontos']} {'ponto' if t['pontos'] == 1 else 'pontos'}"
    limites = page.locator("#pontos").inner_text()
    assert f"até {regras['raio_m']} m" in limites and f"No máximo {regras['max_itens']} itens por dia." in limites
    assert p.erros == [], p.erros

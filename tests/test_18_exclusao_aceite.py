"""
Aceite dos Termos no cadastro e exclusão de conta (Google Maps bloqueado).

Parte 1 — interface. O aceite roda sem criar usuário (a chamada de cadastro é interceptada). A exclusão usa um login
real, mas o RPC `excluir_minha_conta` é simulado: o usuário de teste NÃO é apagado (veja a limpeza em
test_11_pontos_banco.py).
Parte 2 — contra o banco real; é PULADA enquanto supabase/08-excluir-conta.sql não estiver aplicado. Um teste cria
o próprio usuário e o exclui pela interface (é o único jeito de provar a exclusão de verdade).
A lógica do SQL (cascata sem órfãos, só a própria conta, permissões) está em test_19_excluir_conta_sql_local.py.
"""

import json

import pytest

from conftest import esperar_lista, supabase_rest
from test_07_layout import ALVOS_PEQUENOS
from test_11_pontos_banco import SENHA, Usuario, entrar_via_api
from test_13_interface_conta import abrir_conta, axe_do_painel, entrar_pela_interface, logar, menu_aberto
from test_16_interface_medalhas import CORS

LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]
NEGADO = (401, 403)
AVISO_ACEITE = "Para criar a conta, marque que você leu e aceita os Termos de uso e a Política de Privacidade."


# ---------------------------------------------------------------------
# Aceite no cadastro
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_sem_aceite_o_cadastro_nao_e_enviado(abrir, largura, altura):
    chamadas = []

    def cadastro(route):
        chamadas.append(route.request.post_data_json)
        route.fulfill(status=500, headers={**CORS, "content-type": "application/json"},
                      body=json.dumps({"code": 500, "error_code": "unexpected_failure", "msg": "Database error saving new user"}))

    p = abrir("/", largura=largura, altura=altura, toque=largura < 900,
              preparar=lambda page: page.route("**/auth/v1/signup", cadastro))
    page = p.page
    esperar_lista(page)
    abrir_conta(page)
    page.click("[data-ir-vista=criar]")

    # A caixa existe, vem desmarcada, tem links para as duas páginas e alvo de toque grande
    caixa = page.locator("#criar-aceite")
    assert not caixa.is_checked()
    rotulo = page.locator("label.aceite")
    assert "Li e aceito os Termos de uso e a Política de Privacidade" in " ".join(rotulo.inner_text().split())
    assert rotulo.locator('a[href="termos.html"]').count() == 1 and rotulo.locator('a[href="privacidade.html"]').count() == 1
    assert all(rotulo.locator(f'a[href="{h}"]').get_attribute("target") == "_blank" for h in ("termos.html", "privacidade.html"))
    assert rotulo.bounding_box()["height"] >= 44 and caixa.bounding_box()["height"] >= 44
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

    # Tudo preenchido, sem marcar: mensagem em português e NENHUMA requisição de cadastro
    page.fill("#criar-email", "sem-aceite@example.com")
    page.fill("#criar-senha", SENHA)
    page.fill("#criar-apelido", "semaceite")
    page.click("#form-criar button[type=submit]")
    assert page.locator("#form-criar .form__erro").inner_text() == AVISO_ACEITE
    page.wait_for_timeout(300)
    assert chamadas == []
    assert page.locator("#painel-conta").is_visible()

    # O rótulo marca a caixa por clique (e por teclado); com ela marcada, o cadastro é enviado
    page.locator("label.aceite").click(position={"x": 10, "y": 10})
    assert caixa.is_checked()
    page.click("#form-criar button[type=submit]")
    page.wait_for_function("document.querySelector('#form-criar .form__erro').textContent.includes('apelido')")
    assert len(chamadas) == 1 and chamadas[0]["email"] == "sem-aceite@example.com"
    assert axe_do_painel(page) == []
    # só o 500 simulado é esperado no console
    assert [e for e in p.erros if "status of 500" not in e] == [], p.erros


def test_aceite_pelo_teclado(abrir):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)
    abrir_conta(page)
    page.click("[data-ir-vista=criar]")
    page.focus("#criar-aceite")
    page.keyboard.press("Space")
    assert page.locator("#criar-aceite").is_checked()
    assert page.evaluate("getComputedStyle(document.querySelector('label.aceite')).outlineStyle") != "none"  # foco visível


# ---------------------------------------------------------------------
# Exclusão de conta — interface (RPC simulado)
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_excluir_conta_exige_digitar_o_apelido(abrir, largura, altura):
    usuario = Usuario(f"del{largura}")
    chamadas = []

    def excluir(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        chamadas.append(1)
        route.fulfill(status=204, headers=CORS)

    p = abrir("/", largura=largura, altura=altura, toque=largura < 900,
              preparar=lambda page: page.route("**/rest/v1/rpc/excluir_minha_conta", excluir))
    page = p.page
    esperar_lista(page)
    logar(page, usuario)
    abrir_conta(page)
    page.wait_for_function("document.querySelector('#resumo-nivel').textContent === 'Semente'")

    # Começa recolhido; abre a confirmação com o apelido à vista
    assert page.locator("#excluir-painel").is_hidden()
    page.click("#excluir-abrir")
    assert page.locator("#excluir-painel").is_visible()
    assert page.locator("#excluir-abrir").is_hidden()
    assert page.locator("#excluir-apelido-alvo").inner_text() == usuario.apelido
    assert "Não dá para desfazer" in page.locator("#excluir-painel").inner_text()
    assert page.evaluate("document.activeElement.id") == "excluir-apelido"
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

    # Apelido errado ou vazio: mensagem e nenhuma chamada
    page.click("#excluir-confirmar")
    assert "não confere" in page.locator("#excluir-erro").inner_text()
    page.fill("#excluir-apelido", usuario.apelido[:-1])
    page.click("#excluir-confirmar")
    assert "não confere" in page.locator("#excluir-erro").inner_text()
    page.wait_for_timeout(200)
    assert chamadas == []

    # Cancelar recolhe, limpa e devolve o foco ao botão
    page.click("#excluir-cancelar")
    assert page.locator("#excluir-painel").is_hidden() and page.locator("#excluir-abrir").is_visible()
    assert page.evaluate("document.activeElement.id") == "excluir-abrir"
    page.click("#excluir-abrir")
    assert page.locator("#excluir-apelido").input_value() == "" and page.locator("#excluir-erro").inner_text() == ""

    # Apelido certo: exclui, sai da sessão e mostra a mensagem
    page.fill("#excluir-apelido", usuario.apelido)
    page.click("#excluir-confirmar")
    page.wait_for_function("document.querySelector('#conta-titulo').textContent === 'Entrar'", timeout=20000)
    assert len(chamadas) == 1
    aviso = page.locator("#conta-aviso")
    assert aviso.is_visible() and "Sua conta foi excluída" in aviso.inner_text()
    assert "foram apagados" in aviso.inner_text() and "saiu da conta" in aviso.inner_text()
    assert "Sua conta foi excluída" in page.locator("#anuncio").inner_text()
    assert page.locator("#form-entrar").is_visible()
    chaves = page.evaluate("Object.keys(localStorage).filter(k => k.includes('auth-token'))")
    assert chaves == []  # a sessão saiu do navegador
    page.keyboard.press("Escape")
    assert page.locator("[data-conta-abrir]").text_content().strip() == "Entrar"
    menu_aberto(page)
    assert page.locator("[data-conta-sair]").is_hidden()
    assert [e for e in p.erros if "status of" not in e] == [], p.erros


def test_erro_ao_excluir_mantem_a_conta_e_avisa(abrir):
    usuario = Usuario("delerr")

    def excluir(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        route.fulfill(status=500, headers={**CORS, "content-type": "application/json"}, body=json.dumps({"message": "falha simulada"}))

    p = abrir("/", largura=375, altura=812, toque=True,
              preparar=lambda page: page.route("**/rest/v1/rpc/excluir_minha_conta", excluir))
    page = p.page
    esperar_lista(page)
    logar(page, usuario)
    abrir_conta(page)
    page.click("#excluir-abrir")
    page.fill("#excluir-apelido", usuario.apelido)
    page.click("#excluir-confirmar")
    page.wait_for_function("document.querySelector('#excluir-erro').textContent.length > 0")
    assert "Não foi possível excluir a conta" in page.locator("#excluir-erro").inner_text()
    assert page.locator("#conta-titulo").inner_text() == usuario.apelido  # continua logada
    assert page.locator("[data-conta-abrir]").text_content().strip() != "Entrar"
    assert page.locator("#excluir-confirmar").get_attribute("aria-busy") is None


# ---------------------------------------------------------------------
# Parte 2 — contra o banco real (precisa do 08-excluir-conta.sql aplicado)
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def banco_com_exclusao():
    status, corpo = supabase_rest("POST", "rpc/excluir_minha_conta", {})
    if status == 404 and isinstance(corpo, dict) and corpo.get("code") == "PGRST202":
        pytest.skip("O banco ainda não tem excluir_minha_conta: aplique supabase/08-excluir-conta.sql no SQL Editor.")
    assert status in NEGADO, (status, corpo)  # anônimo não executa


def test_banco_anonimo_nao_exclui_nada(banco_com_exclusao):
    assert supabase_rest("POST", "rpc/excluir_minha_conta", {})[0] in NEGADO


def test_banco_exclusao_ponta_a_ponta_pela_interface(abrir, pontos_db, banco_com_exclusao):
    """Cria o PRÓPRIO usuário, registra um descarte real, exclui pela interface e confere que nada sobrou."""
    from test_13_interface_conta import abrir_cartao, esperar_localizacao_automatica, posicao

    ponto = pontos_db[0]
    usuario = Usuario("delreal")
    apelido = usuario.apelido
    status, corpo = usuario.rpc("registrar_descarte", {
        "p_ponto_id": ponto["id"], "p_tipo_id": 3, "p_quantidade": 1,
        "p_lat": ponto["latitude"] + 0.0005, "p_lng": ponto["longitude"]})
    assert status == 200, corpo
    no_ranking = lambda: [l["apelido"] for l in supabase_rest("POST", "rpc/ranking", {"p_periodo": "geral", "p_cidade": None, "p_limite": 50})[1]]
    assert apelido in no_ranking()

    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)
    logar(page, usuario)
    abrir_conta(page)
    page.click("#excluir-abrir")
    page.fill("#excluir-apelido", apelido)
    page.click("#excluir-confirmar")
    page.wait_for_function("document.querySelector('#conta-titulo').textContent === 'Entrar'", timeout=20000)
    assert "Sua conta foi excluída" in page.locator("#conta-aviso").inner_text()

    # O banco confirma: não entra mais, o token antigo não vale, o apelido sumiu do ranking
    status, corpo = entrar_via_api(usuario.email)
    assert status == 400 and corpo.get("error_code") == "invalid_credentials", (status, corpo)
    assert usuario.rpc("meu_resumo")[0] != 200
    assert apelido not in no_ranking()
    assert [e for e in p.erros if "status of" not in e] == [], p.erros

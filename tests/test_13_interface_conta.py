"""
Interface de conta e de registrar descarte (painéis na página única), com o Google Maps bloqueado.
A posição do usuário é simulada pelo Playwright. Cria usuários reais `teste-ecotroca-*@example.com`
(veja a limpeza em test_11_pontos_banco.py).
"""

import re

import pytest

from conftest import esperar_lista, supabase_rest
from test_07_layout import ALVOS_PEQUENOS
from test_10_desempenho_a11y import AXE
from test_11_pontos_banco import DOMINIO, RODADA, SENHA, Usuario, cadastrar_via_api

LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]

LONGE_DEMAIS = "Você precisa estar a até 200 m do ponto de coleta para registrar o descarte."
SEM_PERMISSAO = "Para registrar o descarte, o site precisa da sua localização."


def posicao(ponto, dlat):
    return {"latitude": ponto["latitude"] + dlat, "longitude": ponto["longitude"]}


# ---------- ajudantes de interface ----------
def menu_aberto(page):
    if page.viewport_size["width"] < 900 and page.locator(".topo__menu").get_attribute("aria-expanded") != "true":
        page.click(".topo__menu")


def abrir_conta(page):
    menu_aberto(page)
    page.click("[data-conta-abrir]")
    page.wait_for_selector("#painel-conta[open]")


def entrar_pela_interface(page, email, senha=SENHA):
    page.fill("#entrar-email", email)
    page.fill("#entrar-senha", senha)
    page.click("#form-entrar button[type=submit]")


def logar(page, usuario):
    abrir_conta(page)
    entrar_pela_interface(page, usuario.email)
    page.wait_for_selector("#painel-conta", state="hidden")


def texto_botao_conta(page):
    return page.locator("[data-conta-abrir]").text_content().strip()


def abrir_cartao(page, ponto):
    """Abre o cartão do ponto e devolve o botão 'Registrar descarte' dele."""
    cartao = page.locator(f'.ponto[data-id="{ponto["id"]}"]')
    botao = cartao.get_by_role("button", name=re.compile("^Registrar descarte"))
    if not botao.is_visible():
        cartao.locator(".ponto__cabeca").click()
    botao.wait_for(state="visible")
    return botao


def esperar_localizacao_automatica(page):
    # Com a permissão já concedida o site localiza sozinho ao abrir e redesenha a lista
    page.wait_for_selector("#lista-pontos .selo--proximo", timeout=25000)


def foco_em(page, seletor):
    return page.evaluate("s => document.activeElement === document.querySelector(s)", seletor)


def axe_do_painel(page):
    page.add_script_tag(url=AXE)
    return page.evaluate(
        """async () => (await axe.run({ include: [['dialog[open]']] },
              { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }))
           .violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)"""
    )


# ---------- cadastro, sair e entrar ----------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_cadastro_sair_e_entrar_pela_interface(abrir, largura, altura):
    existente = Usuario(f"uiex{largura}")  # só para provar o erro de apelido repetido
    apelido = f"t{RODADA}u{largura}"
    email = f"teste-ecotroca-{RODADA}-ui{largura}@{DOMINIO}"

    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    assert texto_botao_conta(page) == "Entrar"
    assert page.locator("[data-conta-sair]").is_hidden()

    # Abre, e Esc fecha devolvendo o foco a quem abriu (no celular, o botão Menu)
    abrir_conta(page)
    assert page.locator("#conta-titulo").inner_text() == "Entrar"
    assert foco_em(page, "#entrar-email")
    page.keyboard.press("Escape")
    assert page.locator("#painel-conta").is_hidden()
    assert foco_em(page, ".topo__menu" if largura < 900 else "[data-conta-abrir]")

    # Painel acessível: sem violações WCAG AA e com alvos de 44 px (vista Criar conta)
    abrir_conta(page)
    page.click("[data-ir-vista=criar]")
    assert page.locator("#conta-titulo").inner_text() == "Criar conta"
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

    # Sem o aceite dos Termos, o cadastro não é enviado (test_17 confere que nenhuma requisição sai)
    page.fill("#criar-email", email)
    page.fill("#criar-senha", SENHA)
    page.fill("#criar-apelido", "ab")
    page.click("#form-criar button[type=submit]")
    assert "aceita os Termos de uso" in page.locator("#form-criar .form__erro").inner_text()
    page.check("#criar-aceite")

    # Apelido inválido: erro do próprio formulário, sem fechar
    page.click("#form-criar button[type=submit]")
    assert "3 a 20 caracteres" in page.locator("#form-criar .form__erro").inner_text()
    assert page.locator("#painel-conta").is_visible()

    # Apelido já em uso (sem diferenciar maiúsculas)
    page.fill("#criar-apelido", existente.apelido.upper())
    page.click("#form-criar button[type=submit]")
    page.wait_for_function("document.querySelector('#form-criar .form__erro').textContent.length > 0 && !document.querySelector('#form-criar button[type=submit]').hasAttribute('aria-busy')")
    assert page.locator("#form-criar .form__erro").inner_text() == "Esse apelido não é válido ou já está em uso."

    # Cadastro válido: entra direto, o painel fecha e o botão vira o apelido
    page.fill("#criar-apelido", apelido)
    page.click("#form-criar button[type=submit]")
    page.wait_for_selector("#painel-conta", state="hidden", timeout=20000)
    assert apelido in texto_botao_conta(page)
    assert "Você entrou como " + apelido in page.locator("#anuncio").inner_text()
    menu_aberto(page)
    assert page.locator("[data-conta-sair]").is_visible()

    # Sair pelo menu
    page.click("[data-conta-sair]")
    page.wait_for_function("document.querySelector('[data-conta-abrir]').textContent.trim() === 'Entrar'")
    assert page.locator("[data-conta-sair]").is_hidden()
    assert page.locator("#anuncio").inner_text() == "Você saiu da conta."
    assert foco_em(page, "[data-conta-abrir]")

    # Entrar de novo: senha errada, depois a certa
    abrir_conta(page)
    entrar_pela_interface(page, email, "senha-errada")
    page.wait_for_function("document.querySelector('#form-entrar .form__erro').textContent.length > 0")
    assert page.locator("#form-entrar .form__erro").inner_text() == "E-mail ou senha incorretos."
    assert page.locator("#painel-conta").is_visible()
    entrar_pela_interface(page, email)
    page.wait_for_selector("#painel-conta", state="hidden", timeout=20000)
    assert apelido in texto_botao_conta(page)

    # A sessão sobrevive a recarregar a página
    page.reload()
    esperar_lista(page)
    page.wait_for_function("a => document.querySelector('[data-conta-abrir]').textContent.includes(a)", arg=apelido)

    # Minha conta: recém-criada, tudo zerado; e Sair dentro do painel
    abrir_conta(page)
    assert page.locator("#conta-titulo").inner_text() == apelido
    page.wait_for_function("document.querySelector('#resumo-nivel').textContent === 'Semente'")
    assert page.locator("#resumo-pontos").inner_text() == "0"
    assert page.locator("#resumo-proximo").inner_text() == "Faltam 50 pontos para o nível Broto."
    assert axe_do_painel(page) == []
    page.click("[data-conta-sair-painel]")
    page.wait_for_selector("#painel-conta", state="hidden")
    assert texto_botao_conta(page) == "Entrar"
    # O navegador registra no console os dois erros HTTP que o teste provocou de propósito
    # (500 do apelido repetido, 400 da senha errada); qualquer outro erro falha.
    inesperados = [e for e in p.erros if e not in (
        "Failed to load resource: the server responded with a status of 500 ()",
        "Failed to load resource: the server responded with a status of 400 ()")]
    assert inesperados == [], p.erros


# ---------- registrar descarte ----------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_registrar_descarte_perto_do_ponto(abrir, pontos_db, largura, altura):
    ponto = pontos_db[0]
    usuario = Usuario(f"desc{largura}")
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900,
              geo=posicao(ponto, 0.0005), permitir_geo=True)  # ~55 m do ponto
    page = p.page
    esperar_lista(page)
    esperar_localizacao_automatica(page)

    # Sem login: o painel de entrada abre, avisa do ponto, e depois de entrar volta para o descarte
    botao = abrir_cartao(page, ponto)
    botao.click()
    page.wait_for_selector("#painel-conta[open]")
    assert ponto["nome"] in page.locator("#conta-aviso").inner_text()
    entrar_pela_interface(page, usuario.email)
    page.wait_for_selector("#painel-descarte[open]", timeout=20000)
    assert page.locator("#painel-conta").is_hidden()
    assert page.locator("#painel-descarte-titulo").inner_text() == ponto["nome"]

    # Tipos vindos do banco, com os pontos de cada um
    page.wait_for_selector("#descarte-tipos .opcao")
    nomes = page.locator("#descarte-tipos .opcao__nome").all_text_contents()
    assert nomes == ["Pilhas e baterias", "Cabos e carregadores", "Celulares", "Computadores e periféricos", "Eletrodomésticos pequenos"]
    assert page.locator("#descarte-tipos .opcao", has_text="Celulares").locator(".opcao__pontos").inner_text() == "20 pontos por item"
    assert axe_do_painel(page) == []
    assert page.evaluate(ALVOS_PEQUENOS) == []

    # Validações do próprio painel, antes de pedir a localização
    page.click("#descarte-confirmar")
    assert page.locator("#descarte-erro").inner_text() == "Escolha o tipo de resíduo."
    page.locator("#descarte-tipos .opcao", has_text="Celulares").click()
    page.fill("#descarte-quantidade", "11")
    page.click("#descarte-confirmar")
    assert page.locator("#descarte-erro").inner_text() == "A quantidade deve ser de 1 a 10 itens."
    page.fill("#descarte-quantidade", "2")
    assert page.locator("#descarte-previa").inner_text() == "Esse descarte vale 40 pontos."

    # Confirma: registra e mostra o resultado com clareza
    page.click("#descarte-confirmar")
    page.wait_for_selector("#descarte-resultado", state="visible", timeout=20000)
    assert page.locator("#descarte-resultado-texto").inner_text() == "+40 pontos. Você agora tem 40 pontos, nível Semente."
    assert "0,34 kg (estimativa)" in page.locator("#descarte-resultado-peso").inner_text()
    assert "Descarte registrado" in page.locator("#anuncio").inner_text()
    assert page.locator("#form-descarte").is_hidden()

    # Fechar devolve o foco ao botão do cartão
    page.click("#descarte-resultado [data-fechar]")
    assert page.locator("#painel-descarte").is_hidden()
    assert foco_em(page, f'.ponto[data-id="{ponto["id"]}"] .ponto__detalhes button.botao:not(.botao--suave)')

    # Perfil atualizado
    abrir_conta(page)
    assert page.locator("#conta-titulo").inner_text() == usuario.apelido
    page.wait_for_function("document.querySelector('#resumo-pontos').textContent === '40'")
    assert page.locator("#resumo-nivel").inner_text() == "Semente"
    assert page.locator("#resumo-barra").evaluate("b => [b.value, b.max]") == [40, 50]
    assert page.locator("#resumo-proximo").inner_text() == "Faltam 10 pontos para o nível Broto."
    assert page.locator("#resumo-descartes").inner_text() == "1"
    assert page.locator("#resumo-itens").inner_text() == "2"
    assert page.locator("#resumo-kg").inner_text() == "0,34 kg (estimativa)"
    assert axe_do_painel(page) == []

    # E o banco confirma
    assert usuario.rpc("meu_resumo")[1]["pontos_total"] == 40
    assert p.erros == [], p.erros


def test_erro_de_longe_do_ponto(abrir, pontos_db):
    ponto = pontos_db[0]
    usuario = Usuario("longe")
    p = abrir("/", largura=375, altura=812, toque=True, geo=posicao(ponto, 0.0019), permitir_geo=True)  # ~211 m
    page = p.page
    esperar_lista(page)
    esperar_localizacao_automatica(page)
    logar(page, usuario)

    abrir_cartao(page, ponto).click()
    page.wait_for_selector("#painel-descarte[open]")
    page.wait_for_selector("#descarte-tipos .opcao")
    page.locator("#descarte-tipos .opcao", has_text="Pilhas").click()
    page.click("#descarte-confirmar")
    page.wait_for_function("document.querySelector('#descarte-erro').textContent.length > 0", timeout=20000)
    assert page.locator("#descarte-erro").inner_text() == LONGE_DEMAIS
    assert page.locator("#descarte-resultado").is_hidden()
    assert not page.locator("#descarte-confirmar").get_attribute("aria-busy")
    assert usuario.rpc("meu_resumo")[1] == {"pontos_total": 0, "nivel": "Semente", "descartes": 0, "itens": 0, "kg_estimados": 0}


def test_erro_de_localizacao_negada_e_so_pede_depois_do_clique(abrir, pontos_db):
    ponto = pontos_db[0]
    usuario = Usuario("semgeo")
    contar = "window.__geo = 0; const g = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation); navigator.geolocation.getCurrentPosition = (...a) => { window.__geo++; return g(...a); };"
    p = abrir("/", largura=1280, altura=900, geo=posicao(ponto, 0.0005), permitir_geo=False,
              preparar=lambda page: page.add_init_script(contar))
    page = p.page
    esperar_lista(page)
    logar(page, usuario)

    abrir_cartao(page, ponto).click()
    page.wait_for_selector("#painel-descarte[open]")
    page.wait_for_selector("#descarte-tipos .opcao")
    page.locator("#descarte-tipos .opcao", has_text="Cabos").click()
    assert page.evaluate("window.__geo") == 0, "o site pediu a localização antes do clique em Confirmar"

    page.click("#descarte-confirmar")
    page.wait_for_function("document.querySelector('#descarte-erro').textContent.length > 0", timeout=20000)
    assert page.locator("#descarte-erro").inner_text().startswith(SEM_PERMISSAO)
    assert page.evaluate("window.__geo") == 1
    assert page.locator("#descarte-resultado").is_hidden()
    assert usuario.rpc("meu_resumo")[1]["descartes"] == 0


def test_limite_do_dia_aparece_em_portugues(abrir, pontos_db):
    ponto = pontos_db[0]
    usuario = Usuario("limite")
    # esgota os 30 itens do dia pela API; o 31º vem pela interface
    cabos = {t["nome"]: t["id"] for t in supabase_rest("GET", "tipos_residuo?select=id,nome")[1]}["Cabos e carregadores"]
    for _ in range(3):
        status, corpo = usuario.rpc("registrar_descarte", {"p_ponto_id": ponto["id"], "p_tipo_id": cabos, "p_quantidade": 10,
                                                            "p_lat": ponto["latitude"], "p_lng": ponto["longitude"]})
        assert status == 200, corpo
    p = abrir("/", largura=375, altura=812, toque=True, geo=posicao(ponto, 0.0005), permitir_geo=True)
    page = p.page
    esperar_lista(page)
    esperar_localizacao_automatica(page)
    logar(page, usuario)
    abrir_cartao(page, ponto).click()
    page.wait_for_selector("#descarte-tipos .opcao")
    page.locator("#descarte-tipos .opcao", has_text="Cabos").click()
    page.click("#descarte-confirmar")
    page.wait_for_function("document.querySelector('#descarte-erro').textContent.length > 0", timeout=20000)
    # O texto vem do banco (com o número da regra de supabase/05); o "quanto ainda cabe" depende da versão aplicada
    assert page.locator("#descarte-erro").inner_text().startswith("O limite é de 30 itens por dia.")


# ---------- sem login nada muda ----------
def test_sem_login_o_mapa_e_a_lista_seguem_iguais(abrir, pontos_db):
    ponto = pontos_db[0]
    chamadas_auth = []
    contar = "window.__geo = 0; const g = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation); navigator.geolocation.getCurrentPosition = (...a) => { window.__geo++; return g(...a); };"

    def preparar(page):
        page.add_init_script(contar)
        page.on("request", lambda r: chamadas_auth.append(r.url) if "/auth/v1/" in r.url else None)

    p = abrir("/", largura=1280, altura=900, preparar=preparar)
    page = p.page
    esperar_lista(page)

    assert page.locator("#lista-pontos .ponto").count() == len(pontos_db)
    assert page.locator("#aviso-demo").is_hidden()
    assert page.locator("dialog[open]").count() == 0
    assert texto_botao_conta(page) == "Entrar"

    # Filtro, abrir um ponto e "Como chegar" funcionam sem conta
    page.locator("#filtros .filtro", has_text="Celulares").click()
    assert page.locator("#lista-pontos .ponto").count() == len([l for l in pontos_db if "Celulares" in l["residuos_aceitos"]])
    page.locator("#filtros .filtro", has_text="Todos").click()
    cartao = page.locator(f'.ponto[data-id="{ponto["id"]}"]')
    cartao.locator(".ponto__cabeca").click()
    assert cartao.get_by_role("link", name=re.compile("^Como chegar")).is_visible()

    # Registrar descarte sem conta só abre a entrada: nada de cadastro nem de localização
    cartao.get_by_role("button", name=re.compile("^Registrar descarte")).click()
    page.wait_for_selector("#painel-conta[open]")
    page.keyboard.press("Escape")
    assert page.locator("dialog[open]").count() == 0
    assert foco_em(page, f'.ponto[data-id="{ponto["id"]}"] .ponto__detalhes button.botao:not(.botao--suave)')
    assert page.evaluate("window.__geo") == 0
    assert chamadas_auth == [], chamadas_auth
    assert p.erros == [], p.erros


def test_modo_demonstracao_esconde_a_conta(abrir):
    def preparar(page):
        cfg = open("js/config.js", encoding="utf-8").read().replace("'https://uqgqyqehykkxlnrnoxml.supabase.co'", "'COLE_A_URL'")
        page.route("**/js/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=cfg))

    p = abrir("/", largura=1280, altura=900, preparar=preparar)
    esperar_lista(p.page)
    assert p.page.locator("#aviso-demo").is_visible()
    assert p.page.locator("[data-conta]").is_hidden()
    p.page.locator("#lista-pontos .ponto__cabeca").first.click()
    assert p.page.get_by_role("button", name=re.compile("^Registrar descarte")).count() == 0
    assert p.erros == [], p.erros

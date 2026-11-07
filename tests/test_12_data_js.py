"""
js/data.js no navegador de verdade (Chromium, Google Maps bloqueado): conta, sessão e pontos.
Usa os usuários de teste criados pela API de Auth (veja test_11_pontos_banco.py para a limpeza).
"""

import pytest

from conftest import supabase_rest
from test_11_pontos_banco import SENHA, Usuario

IMPORTAR = "const d = await import('/js/data.js');"


def chamar(page, corpo_js, arg=None):
    """Executa JS que usa `d` (o módulo data.js) e devolve o resultado. Erros viram {erro: {codigo, mensagem}}."""
    return page.evaluate(
        "async (arg) => { " + IMPORTAR + " try { " + corpo_js + " } catch (e) { return { erro: { codigo: e.codigo, mensagem: e.message, nome: e.name } }; } }",
        arg,
    )


@pytest.fixture(scope="module")
def fran():
    return Usuario("fran")


@pytest.fixture
def pagina(abrir):
    p = abrir("/", largura=1280, altura=900)  # Maps bloqueado por padrão
    p.page.wait_for_selector("#lista-pontos .ponto", timeout=25000)
    return p


def test_sem_login_o_site_continua_igual(pagina, pontos_db):
    page = pagina.page
    assert chamar(page, "return await d.sessaoAtual();") is None
    assert page.locator("#lista-pontos .ponto").count() == len(pontos_db)
    assert page.locator("#aviso-demo").is_hidden()
    assert pagina.erros == [], pagina.erros


def test_tipos_de_residuo(pagina):
    tipos = chamar(pagina.page, "return await d.listarTiposResiduo();")
    assert [t["nome"] for t in tipos] == [
        "Pilhas e baterias", "Cabos e carregadores", "Celulares", "Computadores e periféricos", "Eletrodomésticos pequenos"]
    assert [t["pontos"] for t in tipos] == [5, 5, 20, 50, 30]
    assert all(isinstance(t["pesoKg"], (int, float)) and t["pesoKg"] > 0 and t["fonte"] for t in tipos)


@pytest.mark.parametrize("apelido", ["ab", "tem espaco", "x" * 21, "açaí", ""])
def test_cadastrar_valida_o_apelido_antes_de_enviar(pagina, apelido):
    requisicoes = []
    pagina.page.on("request", lambda r: requisicoes.append(r.url) if "/auth/v1/signup" in r.url else None)
    r = chamar(pagina.page, "return await d.cadastrar('alguem@example.com', 'senha-ok-123', arg);", apelido)
    assert r["erro"]["codigo"] == "apelido_invalido"
    assert "3 a 20 caracteres" in r["erro"]["mensagem"]
    assert requisicoes == [], "o formulário enviou o cadastro mesmo com apelido inválido"


def test_cadastrar_valida_email_e_senha(pagina):
    r = chamar(pagina.page, "return await d.cadastrar('sem-arroba', 'senha-ok-123', 'apelido_ok');")
    assert r["erro"]["codigo"] == "email_invalido" and r["erro"]["mensagem"] == "Informe um e-mail válido."
    r = chamar(pagina.page, "return await d.cadastrar('a@example.com', '123', 'apelido_ok');")
    assert r["erro"]["codigo"] == "senha_curta"


def test_cadastrar_apelido_repetido_mostra_a_mensagem_pedida(pagina, fran):
    # O apelido já existe: o trigger recusa e o Auth devolve "Database error saving new user"
    r = chamar(pagina.page, "return await d.cadastrar(arg.email, arg.senha, arg.apelido);",
               {"email": f"teste-ecotroca-dup-{fran.sufixo}@example.com", "senha": SENHA, "apelido": fran.apelido})
    assert r["erro"]["mensagem"] == "Esse apelido não é válido ou já está em uso."
    # e a conta não foi criada
    assert supabase_rest("POST", "token?grant_type=password",
                         {"email": f"teste-ecotroca-dup-{fran.sufixo}@example.com", "password": SENHA}, base="auth/v1")[0] >= 400


def test_entrar_senha_errada(pagina, fran):
    r = chamar(pagina.page, "return await d.entrar(arg.email, 'senha-errada');", {"email": fran.email})
    assert r["erro"]["mensagem"] == "E-mail ou senha incorretos."
    assert chamar(pagina.page, "return await d.sessaoAtual();") is None


def test_fluxo_completo_com_sessao_persistente(pagina, fran, pontos_db):
    page = pagina.page
    ponto = pontos_db[0]
    cred = {"email": fran.email, "senha": SENHA}
    tid = chamar(page, "return (await d.listarTiposResiduo()).find(t => t.nome === 'Pilhas e baterias').id;")

    entrou = chamar(page, "const r = await d.entrar(arg.email, arg.senha); return { email: r.usuario.email, token: !!r.sessao.access_token };", cred)
    assert entrou == {"email": fran.email, "token": True}
    assert chamar(page, "return (await d.sessaoAtual()).user.email;") == fran.email

    # persistSession: true → a sessão sobrevive a recarregar a página
    chaves = page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('sb-') && k.endsWith('-auth-token'))")
    assert len(chaves) == 1, chaves
    page.reload()
    page.wait_for_selector("#lista-pontos .ponto", timeout=25000)
    assert chamar(page, "return (await d.sessaoAtual()).user.email;") == fran.email

    # Recusas traduzidas
    longe = {"t": tid, "p": ponto["id"], "lat": ponto["latitude"] + 0.0019, "lng": ponto["longitude"]}
    r = chamar(page, "return await d.registrarDescarte(arg.p, arg.t, 1, arg.lat, arg.lng);", longe)
    assert r["erro"]["codigo"] == "longe_do_ponto" and "200 m" in r["erro"]["mensagem"]
    for q, esperado in ((0, "quantidade_invalida"), (11, "quantidade_invalida")):
        r = chamar(page, "return await d.registrarDescarte(arg.p, arg.t, arg.q, arg.lat, arg.lng);",
                   {"t": tid, "p": ponto["id"], "q": q, "lat": ponto["latitude"], "lng": ponto["longitude"]})
        assert r["erro"]["codigo"] == esperado and r["erro"]["mensagem"] == "A quantidade deve ser de 1 a 10 itens."
    r = chamar(page, "return await d.registrarDescarte('00000000-0000-0000-0000-000000000000', 1, 1, arg.lat, arg.lng);",
               {"lat": ponto["latitude"], "lng": ponto["longitude"]})
    assert r["erro"]["codigo"] == "ponto_inexistente"
    r = chamar(page, "return await d.registrarDescarte(arg.p, 999, 1, arg.lat, arg.lng);",
               {"p": ponto["id"], "lat": ponto["latitude"], "lng": ponto["longitude"]})
    assert r["erro"]["codigo"] == "tipo_inexistente"
    r = chamar(page, "return await d.registrarDescarte(arg.p, 1, 1, NaN, arg.lng);", {"p": ponto["id"], "lng": ponto["longitude"]})
    assert r["erro"]["codigo"] == "coordenadas_invalidas"

    # Registro válido (tipo 1 = Pilhas e baterias, 5 pontos cada)
    perto = {"t": tid, "p": ponto["id"], "lat": ponto["latitude"] + 0.0005, "lng": ponto["longitude"]}
    r = chamar(page, "return await d.registrarDescarte(arg.p, arg.t, 3, arg.lat, arg.lng);", perto)
    assert r["pontosGanhos"] == 15 and r["pontosTotal"] == 15 and r["nivel"] == "Semente"
    assert r["pesoKgEstimado"] == pytest.approx(0.075)
    resumo = chamar(page, "return await d.meuResumo();")
    assert resumo == {"pontosTotal": 15, "nivel": "Semente", "descartes": 1, "itens": 3, "kgEstimados": pytest.approx(0.075)}

    # Sair: a sessão some, e as funções de conta passam a pedir login
    chamar(page, "await d.sair(); return true;")
    assert chamar(page, "return await d.sessaoAtual();") is None
    assert page.evaluate("Object.keys(localStorage).filter(k => k.endsWith('-auth-token')).length") == 0
    for js in ("return await d.meuResumo();", "return await d.registrarDescarte(arg.p, arg.t, 1, arg.lat, arg.lng);"):
        r = chamar(page, js, perto)
        assert r["erro"]["codigo"] == "nao_logado" and r["erro"]["mensagem"] == "Entre na sua conta para continuar.", r

    # O mapa/lista seguem funcionando depois de tudo isso
    assert page.locator("#lista-pontos .ponto").count() == len(pontos_db)
    assert [e for e in pagina.erros if "Failed to load resource" not in e and "42501" not in e and "401" not in e] == [], pagina.erros


def test_modo_demonstracao_nao_tem_conta(abrir):
    # Sem Supabase configurado a conta não existe, mas a lista de exemplo continua funcionando
    def preparar(page):
        cfg = open("js/config.js", encoding="utf-8").read().replace(
            "'https://uqgqyqehykkxlnrnoxml.supabase.co'", "'COLE_A_URL'")
        page.route("**/js/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=cfg))

    p = abrir("/", preparar=preparar)
    p.page.wait_for_selector("#lista-pontos .ponto", timeout=25000)
    assert p.page.locator("#aviso-demo").is_visible()
    assert chamar(p.page, "return await d.sessaoAtual();") is None
    r = chamar(p.page, "return await d.entrar('a@example.com', 'x');")
    assert r["erro"]["codigo"] == "sem_supabase"


def test_limite_de_tentativas_do_auth_vira_mensagem_clara(abrir):
    # Resposta 429 simulada: não gasta o limite real do Auth
    def preparar(page):
        def limite(route):
            cors = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, OPTIONS"}
            if route.request.method == "OPTIONS":
                return route.fulfill(status=204, headers=cors)
            route.fulfill(status=429, headers={**cors, "content-type": "application/json"},
                          body='{"code":429,"error_code":"over_request_rate_limit","msg":"Request rate limit reached"}')
        page.route("**/auth/v1/signup", limite)
        page.route("**/auth/v1/token**", limite)

    p = abrir("/", largura=1280, altura=900, preparar=preparar)
    p.page.wait_for_selector("#lista-pontos .ponto", timeout=25000)
    esperado = "Muitas tentativas em pouco tempo. Espere alguns minutos e tente de novo."
    r = chamar(p.page, "return await d.cadastrar('alguem@example.com', 'senha-ok-123', 'apelido_ok');")
    assert r["erro"]["codigo"] == "muitas_tentativas" and r["erro"]["mensagem"] == esperado
    r = chamar(p.page, "return await d.entrar('alguem@example.com', 'senha-ok-123');")
    assert r["erro"]["codigo"] == "muitas_tentativas" and r["erro"]["mensagem"] == esperado

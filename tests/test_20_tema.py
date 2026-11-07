"""
Tema de cores: claro, escuro e automático (segue o aparelho). Google Maps bloqueado; nada aqui cria usuário.

Cobre: nenhuma cor fixa fora das variáveis, os dois blocos escuros iguais, contraste WCAG AA dos pares de cor
medidos nos DOIS temas (e o claro idêntico ao que era antes), axe nas seções principais em 375 e 1280 px,
o hero legível sobre a foto, o botão (aria-pressed, alvos de 44 px, teclado), a escolha que permanece depois de
recarregar, o automático acompanhando o aparelho, o site sem localStorage, o modo demonstração e as páginas
Privacidade, Termos e 404.
"""

import re
from pathlib import Path

import pytest
from PIL import Image
import io

from conftest import esperar_lista
from test_07_layout import ALVOS_PEQUENOS
from test_10_desempenho_a11y import AXE, _luminancia

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "css" / "styles.css").read_text(encoding="utf-8")
LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]
CHAVE = "ecotroca-tema"
PAPEL_CLARO, PAPEL_ESCURO = "rgb(250, 248, 243)", "rgb(20, 18, 15)"
META_CLARO, META_ESCURO = "#FAF8F3", "#14120F"
TEMAS = ["light", "dark"]


# ---------------------------------------------------------------------
# CSS (sem navegador)
# ---------------------------------------------------------------------
def _bloco(inicio):
    """Texto de um bloco CSS que começa em `inicio` (até a chave que o fecha)."""
    i = CSS.index(inicio)
    abre = CSS.index("{", i)
    nivel, j = 0, abre
    while True:
        if CSS[j] == "{":
            nivel += 1
        elif CSS[j] == "}":
            nivel -= 1
            if nivel == 0:
                return CSS[i:j + 1]
        j += 1


def _declaracoes(bloco):
    corpo = bloco[bloco.index("{") + 1:bloco.rindex("}")]
    corpo = re.sub(r"/\*.*?\*/", "", corpo, flags=re.S)
    if "{" in corpo:  # bloco @media: o conteúdo é a regra de dentro
        corpo = corpo[corpo.index("{") + 1:corpo.rindex("}")]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+|color-scheme)\s*:\s*([^;]+);", corpo)}


def test_o_tema_escuro_tem_os_dois_blocos_iguais_e_color_scheme():
    por_atributo = _declaracoes(_bloco(':root[data-theme="dark"]'))
    por_aparelho = _declaracoes(_bloco("@media (prefers-color-scheme: dark)"))
    assert por_atributo == por_aparelho and len(por_atributo) > 15
    assert por_atributo["color-scheme"] == "dark"
    assert _declaracoes(_bloco(":root {"))["color-scheme"] == "light"
    assert ':root:not([data-theme="light"])' in _bloco("@media (prefers-color-scheme: dark)")


def test_o_tema_escuro_so_redefine_variaveis_que_existem_no_claro():
    claro = _declaracoes(_bloco(":root {"))
    escuro = _declaracoes(_bloco(':root[data-theme="dark"]'))
    assert set(escuro) - {"color-scheme"} <= set(claro), set(escuro) - set(claro)


def test_nenhuma_cor_fixa_fora_das_variaveis():
    sem_temas = CSS
    for inicio in (":root {", ':root[data-theme="dark"]', "@media (prefers-color-scheme: dark)"):
        sem_temas = sem_temas.replace(_bloco(inicio), "")
    sem_comentarios = re.sub(r"/\*.*?\*/", "", sem_temas, flags=re.S)
    fixas = [l.strip() for l in sem_comentarios.splitlines() if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", l)]
    # Única exceção: o balão do mapa (o InfoWindow do Google é branco nos dois temas), que fixa as próprias cores
    assert [l for l in fixas if not l.startswith(".balao {")] == [], fixas


def test_toda_pagina_aplica_o_tema_salvo_antes_de_desenhar():
    for arquivo in ("index.html", "privacidade.html", "termos.html", "404.html"):
        html = (RAIZ / arquivo).read_text(encoding="utf-8")
        cabeca = html[:html.index("</head>")]
        assert f"localStorage.getItem('{CHAVE}')" in cabeca and "try{" in cabeca, arquivo
        assert cabeca.index("localStorage.getItem") < cabeca.index("styles.css"), arquivo  # antes de carregar o CSS
        assert 'name="theme-color" content="#FAF8F3"' in html, arquivo  # o padrão continua claro


# ---------------------------------------------------------------------
# Ajudantes de navegador
# ---------------------------------------------------------------------
def tema_salvo(valor):
    """`preparar` do abrir(): grava a escolha em localStorage antes de a página carregar (o mesmo caminho do botão)."""
    return lambda page: page.add_init_script(f"try{{localStorage.setItem('{CHAVE}','{valor}')}}catch(e){{}}")


def fundo(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def meta(page):
    return page.evaluate("document.querySelector('meta[name=theme-color]').getAttribute('content')")


def atributo(page):
    return page.evaluate("document.documentElement.getAttribute('data-theme')")


def aberto(abrir, tema, largura=1280, altura=900, caminho="/", **kw):
    p = abrir(caminho, largura=largura, altura=altura, toque=largura < 900, preparar=tema_salvo(tema), **kw)
    if caminho == "/":
        esperar_lista(p.page)
    return p


def axe_da_pagina(page):
    page.add_script_tag(url=AXE)
    return page.evaluate(
        """async () => (await axe.run({ exclude: [['#mapa-google']] },
              { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }))
           .violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)"""
    )


def escolher(page, texto):
    """Clica numa opção do botão de tema (no celular, abre o menu antes)."""
    if page.viewport_size["width"] < 900 and page.locator(".topo__menu").get_attribute("aria-expanded") != "true":
        page.click(".topo__menu")
    page.locator(".tema__opcao", has=page.locator(".tema__rotulo", has_text=re.compile(f"^{texto}$"))).click()


# ---------------------------------------------------------------------
# Contraste dos pares de cor (mesmos pares medidos antes de mexer no tema)
# ---------------------------------------------------------------------
# (nome, cor do texto/elemento, cor do fundo, mínimo): 4,5 para texto normal e 3 para elementos gráficos
PARES = [
    ("tinta/papel", "--tinta", "--papel", 4.5),
    ("tinta-2/papel", "--tinta-2", "--papel", 4.5),
    ("verde-700/papel", "--verde-700", "--papel", 4.5),
    ("verde-800/papel", "--verde-800", "--papel", 4.5),
    ("verde-900/papel", "--verde-900", "--papel", 4.5),
    ("alerta/papel", "--alerta", "--papel", 4.5),
    ("tinta/papel-2", "--tinta", "--papel-2", 4.5),
    ("tinta-2/papel-2", "--tinta-2", "--papel-2", 4.5),
    ("tinta/verde-100", "--tinta", "--verde-100", 4.5),
    ("tinta-2/verde-100", "--tinta-2", "--verde-100", 4.5),
    ("verde-900/verde-100", "--verde-900", "--verde-100", 4.5),
    ("verde-800/verde-100", "--verde-800", "--verde-100", 4.5),
    ("verde-700/verde-100", "--verde-700", "--verde-100", 4.5),
    ("alerta/verde-100", "--alerta", "--verde-100", 4.5),
    ("tinta/verde-50", "--tinta", "--verde-50", 4.5),
    ("tinta-2/verde-50", "--tinta-2", "--verde-50", 4.5),
    ("sobre-acao/acao (botão, selo)", "--sobre-acao", "--acao", 4.5),
    ("sobre-acao/acao-hover (botão)", "--sobre-acao", "--acao-hover", 4.5),
    ("sobre-acao/perigo (excluir)", "--sobre-acao", "--perigo", 4.5),
    ("sobre-acao/perigo-hover", "--sobre-acao", "--perigo-hover", 4.5),
    ("papel/tinta (filtro ativo)", "--papel", "--tinta", 4.5),
    ("sobre-escuro/fundo-escuro (passos)", "--sobre-escuro", "--fundo-escuro", 4.5),
    ("sobre-escuro-2/fundo-escuro (passos)", "--sobre-escuro-2", "--fundo-escuro", 4.5),
    ("verde-400/fundo-escuro (passos)", "--verde-400", "--fundo-escuro", 4.5),
    ("claro-texto/claro-fundo (botão claro)", "--claro-texto", "--claro-fundo", 4.5),
    ("claro-texto/claro-hover", "--claro-texto", "--claro-hover", 4.5),
    ("borda do campo: tinta-2/papel", "--tinta-2", "--papel", 3.0),
    ("borda do campo: tinta-2/papel-2", "--tinta-2", "--papel-2", 3.0),
    ("foco e marcas: verde-700/papel", "--verde-700", "--papel", 3.0),
    ("foco e marcas: verde-700/verde-100", "--verde-700", "--verde-100", 3.0),
    ("botão sobre a página: acao/papel", "--acao", "--papel", 3.0),
]

# Razões medidas ANTES de criar o tema escuro (tema claro). O claro não pode mudar.
BASE_CLARO = {
    "tinta/papel": 16.13, "tinta-2/papel": 8.13, "verde-700/papel": 4.83, "verde-800/papel": 7.76,
    "verde-900/papel": 10.78, "alerta/papel": 6.40, "tinta/papel-2": 14.90, "tinta-2/papel-2": 7.51,
    "tinta/verde-100": 15.22, "tinta-2/verde-100": 7.67, "verde-900/verde-100": 10.17, "verde-800/verde-100": 7.33,
    "verde-700/verde-100": 4.56, "alerta/verde-100": 6.04, "tinta/verde-50": 15.85, "tinta-2/verde-50": 7.98,
    "sobre-acao/acao (botão, selo)": 5.13, "sobre-acao/acao-hover (botão)": 11.44, "sobre-acao/perigo (excluir)": 6.79,
    "papel/tinta (filtro ativo)": 16.13, "sobre-escuro/fundo-escuro (passos)": 10.78, "verde-400/fundo-escuro (passos)": 4.84,
}

LER_CORES = """
(nomes) => {
  const saida = {};
  const el = document.createElement('span');
  document.body.append(el);
  for (const n of nomes) { el.style.color = `var(${n})`; saida[n] = getComputedStyle(el).color; }
  el.remove();
  return saida;
}
"""


def _canais(css):
    return [float(v) for v in re.findall(r"[\d.]+", css)[:3]]


def razao(a, b):
    la, lb = _luminancia(_canais(a)), _luminancia(_canais(b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def razoes(page):
    nomes = sorted({n for _, f, b, _ in PARES for n in (f, b)})
    cores = page.evaluate(LER_CORES, nomes)
    return {nome: razao(cores[f], cores[b]) for nome, f, b, _ in PARES}, cores


@pytest.mark.parametrize("tema", TEMAS)
def test_contraste_aa_dos_pares_de_cor_nos_dois_temas(abrir, tema):
    p = aberto(abrir, tema)
    assert atributo(p.page) == tema
    medidas, _ = razoes(p.page)
    ruins = [f"{n}: {medidas[n]:.2f}:1 (mínimo {m}:1)" for n, _, _, m in PARES if medidas[n] < m]
    assert ruins == [], "\n".join(ruins)


def test_o_tema_claro_nao_mudou(abrir):
    p = aberto(abrir, "light")
    medidas, _ = razoes(p.page)
    mudou = [f"{n}: era {BASE_CLARO[n]:.2f}, agora {medidas[n]:.2f}" for n in BASE_CLARO if abs(medidas[n] - BASE_CLARO[n]) > 0.011]
    assert mudou == [], "\n".join(mudou)


def test_automatico_usa_exatamente_as_cores_do_tema_explicito(abrir):
    explicito = {}
    for tema in TEMAS:
        explicito[tema] = razoes(aberto(abrir, tema).page)[1]
    for esquema, tema in (("light", "light"), ("dark", "dark")):
        p = abrir("/", largura=1280, altura=900)  # sem escolha salva = Automático
        p.page.emulate_media(color_scheme=esquema)
        esperar_lista(p.page)
        assert atributo(p.page) is None
        assert razoes(p.page)[1] == explicito[tema], esquema


# ---------------------------------------------------------------------
# axe e hero
# ---------------------------------------------------------------------
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_axe_wcag_aa_nas_secoes_nos_dois_temas(abrir, pontos_db, tema, largura, altura):
    p = aberto(abrir, tema, largura, altura, movimento="reduce")
    page = p.page
    page.locator("#lista-pontos .ponto__cabeca").first.click()
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert axe_da_pagina(page) == []
    assert p.erros == [], p.erros


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_axe_nos_paineis_nos_dois_temas(abrir, tema, largura, altura):
    p = aberto(abrir, tema, largura, altura)
    page = p.page
    if largura < 900:
        page.click(".topo__menu")
    page.click("[data-conta-abrir]")
    page.wait_for_selector("#painel-conta[open]")
    for vista in ("entrar", "criar"):
        if vista == "criar":
            page.click("[data-ir-vista=criar]")
            page.locator("#criar-aceite").check()  # marca desenhada também confere
        page.add_script_tag(url=AXE)
        violacoes = page.evaluate(
            """async () => (await axe.run({ include: [['dialog[open]']] },
                  { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } }))
               .violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)"""
        )
        assert violacoes == [], (vista, violacoes)


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("largura,altura", [(375, 812), (1280, 900), (2000, 1100)])
def test_hero_legivel_sobre_a_foto_nos_dois_temas(abrir, tema, largura, altura):
    """Mesma medição do test_10 (pior pixel da foto atrás de cada linha), agora nos dois temas. O texto é sempre claro."""
    p = aberto(abrir, tema, largura, altura)
    page = p.page
    page.wait_for_function("document.querySelector('.hero__foto img').complete")
    alvos = {".hero__sobretitulo": 4.5, ".hero__titulo": 3.0, ".hero__apoio": 4.5, ".hero__link": 4.5}
    cores = {s: page.evaluate(f"getComputedStyle(document.querySelector('{s}')).color") for s in alvos}
    caixas = {s: page.locator(s).bounding_box() for s in alvos}
    page.add_style_tag(content=".hero__conteudo :is(p, h1, a:not(.botao)) { color: transparent !important; text-decoration-color: transparent !important; }")
    foto = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    for seletor, minimo in alvos.items():
        texto = _luminancia(_canais(cores[seletor]))
        assert texto > 0.6, f"{seletor}: texto escuro sobre a foto ({cores[seletor]})"  # nunca preto sobre a foto
        c = caixas[seletor]
        recorte = foto.crop((int(c["x"]), int(c["y"]), int(c["x"] + c["width"]), int(c["y"] + c["height"])))
        dados = recorte.tobytes()
        lums = sorted(_luminancia(dados[i:i + 3]) for i in range(0, len(dados), 3))
        claro_do_fundo = lums[int(len(lums) * 0.98) - 1]
        r = (max(texto, claro_do_fundo) + 0.05) / (min(texto, claro_do_fundo) + 0.05)
        assert r >= minimo, f"{seletor} em {largura}px, tema {tema}: {r:.2f}:1 (mínimo {minimo}:1)"


# ---------------------------------------------------------------------
# O botão
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_botao_alterna_marca_aria_pressed_e_atualiza_o_meta(abrir, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    if largura < 900:
        page.click(".topo__menu")
    opcoes = page.locator(".tema__opcao")
    assert opcoes.count() == 3 and page.locator(".tema").get_attribute("role") == "group"
    assert page.locator(".tema").get_attribute("aria-label") == "Tema de cores"
    assert [o.locator(".tema__rotulo").text_content() for o in opcoes.all()] == ["Automático", "Claro", "Escuro"]
    pressionados = lambda: [o.get_attribute("aria-pressed") for o in opcoes.all()]
    assert pressionados() == ["true", "false", "false"]
    assert atributo(page) is None and meta(page) == META_CLARO

    escolher(page, "Escuro")
    assert pressionados() == ["false", "false", "true"] and atributo(page) == "dark"
    assert fundo(page) == PAPEL_ESCURO and meta(page) == META_ESCURO
    assert page.evaluate("localStorage.getItem('%s')" % CHAVE) == "dark"
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "dark"
    assert "Tema: Escuro." in page.locator("#anuncio").inner_text()

    escolher(page, "Claro")
    assert pressionados() == ["false", "true", "false"] and atributo(page) == "light"
    assert fundo(page) == PAPEL_CLARO and meta(page) == META_CLARO
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "light"

    escolher(page, "Automático")
    assert pressionados() == ["true", "false", "false"] and atributo(page) is None
    assert page.evaluate("localStorage.getItem('%s')" % CHAVE) is None
    assert p.erros == [], p.erros


@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_botao_tem_alvos_de_44px_e_o_foco_aparece(abrir, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    if largura < 900:
        page.click(".topo__menu")
    for opcao in page.locator(".tema__opcao").all():
        caixa = opcao.bounding_box()
        assert caixa["width"] >= 44 and caixa["height"] >= 44, caixa
    assert page.evaluate(ALVOS_PEQUENOS) == []
    # Teclado: Tab chega ao botão, Enter/Espaço escolhem, e o foco tem contorno
    page.focus(".tema__opcao[data-tema=auto]")
    page.keyboard.press("Tab")  # chega por teclado: o contorno de foco precisa aparecer
    assert page.evaluate("document.activeElement.dataset.tema") == "light"
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none"
    page.keyboard.press("Enter")
    assert atributo(page) == "light"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.tema") == "dark"
    page.keyboard.press("Space")
    assert atributo(page) == "dark"


@pytest.mark.parametrize("largura", [900, 1024, 1280])
def test_cabecalho_cabe_com_o_botao_de_tema(abrir, largura):
    p = abrir("/", largura=largura, altura=800)
    page = p.page
    esperar_lista(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    caixas = page.evaluate("""() => {
        const r = s => document.querySelector(s).getBoundingClientRect();
        const lis = [...document.querySelectorAll('#menu-principal > ul > li')].map(li => li.getBoundingClientRect());
        return { marca: r('.topo__marca'), lis: lis.map(b => [b.left, b.right, b.top, b.bottom]), barra: r('.topo__barra') };
    }""")
    assert caixas["lis"][0][0] >= caixas["marca"]["right"] - 1, "o menu encosta no logo"
    assert caixas["lis"][-1][1] <= caixas["barra"]["right"] + 1
    alturas = {round(l[3] - l[2]) for l in caixas["lis"]}
    assert max(alturas) <= 60, f"o menu quebrou de linha: {alturas}"  # uma linha só


# ---------------------------------------------------------------------
# Persistência, automático e localStorage indisponível
# ---------------------------------------------------------------------
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_a_escolha_permanece_depois_de_recarregar(abrir, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    escolher(page, "Escuro")
    page.reload()
    esperar_lista(page)
    assert atributo(page) == "dark" and fundo(page) == PAPEL_ESCURO and meta(page) == META_ESCURO
    if largura < 900:
        page.click(".topo__menu")
    assert page.locator(".tema__opcao[data-tema=dark]").get_attribute("aria-pressed") == "true"
    escolher(page, "Claro")
    page.reload()
    esperar_lista(page)
    assert atributo(page) == "light" and fundo(page) == PAPEL_CLARO
    escolher(page, "Automático")
    page.reload()
    esperar_lista(page)
    assert atributo(page) is None


def test_o_tema_salvo_vale_mesmo_se_o_modulo_do_botao_falhar(abrir):
    """O script curto do <head> basta: nada de piscar de claro para escuro, nem dependência do js/tema.js."""
    p = abrir("/", largura=1280, altura=900, preparar=lambda page: (tema_salvo("dark")(page), page.route("**/js/tema.js", lambda r: r.abort())))
    p.page.wait_for_selector("h1")
    assert atributo(p.page) == "dark" and fundo(p.page) == PAPEL_ESCURO


def test_automatico_segue_o_aparelho_e_avisa_o_meta(abrir):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)
    page.emulate_media(color_scheme="dark")
    assert atributo(page) is None and fundo(page) == PAPEL_ESCURO
    page.wait_for_function("document.querySelector('meta[name=theme-color]').content.toLowerCase() === '#14120f'")
    page.emulate_media(color_scheme="light")
    assert fundo(page) == PAPEL_CLARO
    page.wait_for_function("document.querySelector('meta[name=theme-color]').content.toLowerCase() === '#faf8f3'")
    # Escolha manual vence o aparelho
    page.emulate_media(color_scheme="dark")
    escolher(page, "Claro")
    assert fundo(page) == PAPEL_CLARO
    page.emulate_media(color_scheme="light")
    escolher(page, "Escuro")
    assert fundo(page) == PAPEL_ESCURO
    # Volta ao Automático: segue o aparelho de novo
    escolher(page, "Automático")
    assert fundo(page) == PAPEL_CLARO
    page.emulate_media(color_scheme="dark")
    assert fundo(page) == PAPEL_ESCURO


def test_sem_localstorage_o_site_funciona_e_o_botao_vale_so_nesta_visita(abrir):
    def sem_storage(page):
        page.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqueado'); } });")

    p = abrir("/", largura=1280, altura=900, preparar=sem_storage)
    page = p.page
    esperar_lista(page)
    assert atributo(page) is None and fundo(page) == PAPEL_CLARO
    escolher(page, "Escuro")
    assert atributo(page) == "dark" and fundo(page) == PAPEL_ESCURO
    escolher(page, "Automático")
    assert atributo(page) is None
    assert [e for e in p.erros if e.startswith("pageerror")] == [], p.erros


def test_o_balao_do_mapa_continua_legivel_no_escuro(abrir):
    """O InfoWindow do Google é branco nos dois temas: texto e link do balão não podem virar claros."""
    p = aberto(abrir, "dark")
    cores = p.page.evaluate("""() => {
        const b = document.createElement('div'); b.className = 'balao';
        b.innerHTML = '<p>Texto</p><a href="#">link</a>'; document.body.append(b);
        return [getComputedStyle(b).color, getComputedStyle(b.querySelector('a')).color];
    }""")
    assert cores == ["rgb(31, 27, 22)", "rgb(46, 125, 50)"]


# ---------------------------------------------------------------------
# Modo demonstração e páginas estáticas
# ---------------------------------------------------------------------
def _demonstracao(tema):
    def preparar(page):
        tema_salvo(tema)(page)
        cfg = (RAIZ / "js" / "config.js").read_text(encoding="utf-8").replace("'https://uqgqyqehykkxlnrnoxml.supabase.co'", "'COLE_A_URL'")
        page.route("**/js/config.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=cfg))

    return preparar


@pytest.mark.parametrize("tema", TEMAS)
def test_modo_demonstracao_respeita_o_tema(abrir, tema):
    p = abrir("/", largura=375, altura=812, toque=True, preparar=_demonstracao(tema), movimento="reduce")
    page = p.page
    esperar_lista(page)
    assert page.locator(".aviso-demo").count() == 1  # é mesmo o modo demonstração
    assert fundo(page) == (PAPEL_ESCURO if tema == "dark" else PAPEL_CLARO)
    assert atributo(page) == tema
    assert axe_da_pagina(page) == []
    page.click(".topo__menu")
    assert page.locator(".tema__opcao[data-tema=%s]" % tema).get_attribute("aria-pressed") == "true"
    assert p.erros == [], p.erros


@pytest.mark.parametrize("caminho", ["/privacidade.html", "/termos.html", "/404.html"])
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_paginas_estaticas_respeitam_o_tema(abrir, caminho, tema, largura, altura):
    p = aberto(abrir, tema, largura, altura, caminho=caminho)
    page = p.page
    page.wait_for_selector("footer")
    assert atributo(page) == tema
    assert fundo(page) == (PAPEL_ESCURO if tema == "dark" else PAPEL_CLARO)
    assert meta(page) == (META_ESCURO if tema == "dark" else META_CLARO) or caminho == "/404.html"
    assert axe_da_pagina(page) == []
    assert p.erros == [], p.erros


@pytest.mark.parametrize("caminho", ["/privacidade.html", "/termos.html"])
def test_paginas_estaticas_seguem_o_aparelho_no_automatico(abrir, caminho):
    p = abrir(caminho, largura=375, altura=812)
    page = p.page
    page.emulate_media(color_scheme="dark")
    page.wait_for_selector("footer")
    assert atributo(page) is None and fundo(page) == PAPEL_ESCURO
    page.wait_for_function("document.querySelector('meta[name=theme-color]').content.toLowerCase() === '#14120f'")
    assert page.evaluate("getComputedStyle(document.querySelector('.documento__revisao')).color") != page.evaluate(
        "getComputedStyle(document.querySelector('.documento__revisao')).backgroundColor")

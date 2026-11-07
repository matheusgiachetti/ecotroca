"""Item 10 — imagens, lazy-loading, teclado, foco visível, contraste (axe-core + medição sobre a foto do hero)."""

import io

import pytest
from PIL import Image

from conftest import esperar_lista, esperar_marcadores

AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


def test_imagens_otimizadas_e_lazy(abrir):
    p = abrir("/", largura=375, altura=812)
    page = p.page
    page.wait_for_load_state("load")
    imagens = page.evaluate(
        """() => [...document.images].filter(img => !img.closest('#mapa-google')).map(img => {
             const r = img.getBoundingClientRect();
             return { src: img.currentSrc || img.src, lazy: img.loading === 'lazy', topo: r.top + scrollY,
                      w: img.getAttribute('width'), h: img.getAttribute('height'), alt: img.getAttribute('alt'),
                      natural: img.naturalWidth, exibida: r.width };
           })"""
    )
    dobra = 812
    for img in imagens:
        assert img["w"] and img["h"], f"sem width/height: {img['src']}"
        assert img["alt"] is not None, f"sem alt: {img['src']}"
        if img["topo"] > dobra:
            assert img["lazy"], f"fora da primeira dobra e sem lazy: {img['src']}"
    hero = page.evaluate("document.querySelector('.hero__foto img').currentSrc")
    assert hero.endswith("hero-768.webp"), hero  # webp e tamanho certo para celular

    # Pesos máximos (bytes) das fotos servidas
    for nome, limite in {"hero-768.webp": 60_000, "hero-1280.webp": 100_000, "hero-2000.webp": 200_000,
                         "descarte-700.webp": 80_000, "descarte-1200.webp": 160_000}.items():
        resposta = page.request.get(f"{page.url.split('#')[0].rstrip('/')}/assets/{nome}")
        assert resposta.ok and len(resposta.body()) <= limite, f"{nome}: {len(resposta.body())} bytes"


def test_metricas_de_carregamento(abrir):
    p = abrir("/", largura=375, altura=812)
    page = p.page
    page.evaluate(
        """() => { window.__lcp = 0; window.__cls = 0;
             new PerformanceObserver(l => l.getEntries().forEach(e => window.__lcp = e.startTime))
               .observe({ type: 'largest-contentful-paint', buffered: true });
             new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) window.__cls += e.value; }))
               .observe({ type: 'layout-shift', buffered: true }); }"""
    )
    esperar_lista(page)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    lcp, cls = page.evaluate("[window.__lcp, window.__cls]")
    assert lcp < 2500, f"LCP {lcp:.0f} ms"
    assert cls < 0.1, f"CLS {cls:.3f}"


def test_teclado_e_foco_visivel(abrir):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)

    page.keyboard.press("Tab")
    pular = page.evaluate("[document.activeElement.className, document.activeElement.getBoundingClientRect().top]")
    assert pular[0] == "pular" and pular[1] >= 0, "link 'Pular para o mapa' não aparece no primeiro Tab"

    sem_foco_visivel = []
    vistos = []
    for _ in range(30):
        page.keyboard.press("Tab")
        info = page.evaluate(
            """() => { const el = document.activeElement; const s = getComputedStyle(el);
                 return { dentroDoMapa: !!el.closest('#mapa-google'), texto: (el.textContent || '').trim().slice(0, 30),
                          outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2,
                          sombra: s.boxShadow !== 'none' }; }"""
        )
        if info["dentroDoMapa"]:
            continue
        vistos.append(info["texto"])
        if not (info["outline"] or info["sombra"]):
            sem_foco_visivel.append(info["texto"])
    assert len(vistos) > 10
    assert sem_foco_visivel == [], sem_foco_visivel

    # Ponto da lista abre com Enter
    cabeca = page.locator("#lista-pontos .ponto__cabeca").first
    cabeca.focus()
    page.keyboard.press("Enter")
    assert cabeca.get_attribute("aria-expanded") == "true"
    # Filtro funciona com Espaço
    filtro = page.locator("#filtros .filtro").nth(2)
    filtro.focus()
    page.keyboard.press("Space")
    assert filtro.get_attribute("aria-pressed") == "true"


@pytest.mark.parametrize("largura", [375, 1280])
def test_axe_wcag_aa(abrir, pontos_db, largura):
    p = abrir("/", largura=largura, altura=900, movimento="reduce")
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, len(pontos_db))
    page.locator("#lista-pontos .ponto__cabeca").first.click()
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    page.add_script_tag(url=AXE)
    resultado = page.evaluate(
        """async () => {
             const r = await axe.run({ exclude: [['#mapa-google']] },
               { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } });
             return r.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`);
           }"""
    )
    assert resultado == [], "\n".join(resultado)


def _luminancia(rgb):
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[:3]
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


@pytest.mark.parametrize("largura,altura", [(375, 812), (1280, 900), (2000, 1100)])
def test_contraste_do_texto_sobre_a_foto_do_hero(abrir, largura, altura):
    """Esconde o texto, fotografa o fundo atrás de cada linha e compara com a cor do texto (pior caso: pixel 98% mais claro)."""
    p = abrir("/", largura=largura, altura=altura)
    page = p.page
    page.wait_for_function("document.querySelector('.hero__foto img').complete")
    alvos = {".hero__sobretitulo": 4.5, ".hero__titulo": 3.0, ".hero__apoio": 4.5, ".hero__link": 4.5}
    cores = {s: page.evaluate(f"getComputedStyle(document.querySelector('{s}')).color") for s in alvos}
    caixas = {s: page.locator(s).bounding_box() for s in alvos}
    page.add_style_tag(content=".hero__conteudo :is(p, h1, a:not(.botao)) { color: transparent !important; text-decoration-color: transparent !important; }")
    foto = Image.open(io.BytesIO(page.screenshot())).convert("RGB")

    for seletor, minimo in alvos.items():
        c = caixas[seletor]
        recorte = foto.crop((int(c["x"]), int(c["y"]), int(c["x"] + c["width"]), int(c["y"] + c["height"])))
        dados = recorte.tobytes()
        lums = sorted(_luminancia(dados[i:i + 3]) for i in range(0, len(dados), 3))
        fundo = lums[int(len(lums) * 0.98) - 1]
        texto = _luminancia([int(v) for v in cores[seletor][4:-1].split(",")[:3]])
        razao = (max(texto, fundo) + 0.05) / (min(texto, fundo) + 0.05)
        assert razao >= minimo, f"{seletor} em {largura}px: {razao:.2f}:1 (mínimo {minimo}:1)"

"""Item 7 — layout em 320, 375, 768 e 1280 px: console limpo, sem rolagem lateral, alvos de toque ≥ 44 px."""

import pytest

from conftest import esperar_lista, esperar_marcadores

LARGURAS = [(320, 640), (375, 812), (768, 1024), (1280, 900)]

# Alvos interativos visíveis. Ficam de fora: controles do próprio Google Maps e
# links no meio de uma frase (exceção "inline" da WCAG 2.5.8 / 2.5.5).
ALVOS_PEQUENOS = """
() => {
  const sel = 'a[href], button, summary, input, select, textarea, [role="button"]';
  const ruins = [];
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('#mapa-google')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const estilo = getComputedStyle(el);
    if (estilo.visibility === 'hidden' || r.bottom + scrollY < 0) continue;      // ex.: "Pular para o mapa" fora da tela
    const pai = el.parentElement;
    const noMeioDoTexto = el.tagName === 'A' && estilo.display === 'inline'
      && pai && pai.textContent.trim() !== el.textContent.trim();
    if (noMeioDoTexto) continue;
    if (r.width < 44 || r.height < 44) {
      ruins.push(`${el.tagName.toLowerCase()}.${el.className || ''} "${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
  }
  return ruins;
}
"""


def _percorrer(page):
    """Rola a página inteira (dispara animações e imagens lazy) e volta ao topo."""
    altura = page.evaluate("document.documentElement.scrollHeight")
    for y in range(0, altura, 400):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(40)
    page.evaluate("window.scrollTo(0, 0)")


@pytest.mark.parametrize("largura,altura", LARGURAS, ids=[f"{l}px" for l, _ in LARGURAS])
def test_layout(abrir, pontos_db, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, len(pontos_db))
    page.locator("#lista-pontos .ponto__cabeca").first.click()  # abre um cartão (botão "Como chegar")
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    _percorrer(page)
    page.wait_for_load_state("networkidle")

    rolagem = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert rolagem[0] <= rolagem[1], f"rolagem horizontal: {rolagem}"

    ruins = page.evaluate(ALVOS_PEQUENOS)
    if largura < 900:  # menu aberto também precisa de alvos grandes
        page.click(".topo__menu")
        ruins += page.evaluate(ALVOS_PEQUENOS)
    assert ruins == [], "alvos menores que 44px:\n" + "\n".join(sorted(set(ruins)))

    assert p.erros == [], p.erros


def test_menu_mobile(abrir):
    p = abrir("/", largura=375, altura=812)
    page = p.page
    botao = page.locator(".topo__menu")
    assert botao.is_visible() and page.locator("#menu-principal").is_hidden()
    botao.click()
    assert botao.get_attribute("aria-expanded") == "true"
    assert page.locator("#menu-principal").is_visible()
    page.keyboard.press("Escape")
    assert botao.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.classList.contains('topo__menu')")
    botao.click()
    page.locator("#menu-principal a", has_text="Dúvidas").click()
    assert page.locator("#menu-principal").is_hidden()
    page.wait_for_function("location.hash === '#duvidas'")

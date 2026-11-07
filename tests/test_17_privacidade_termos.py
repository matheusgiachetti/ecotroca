"""
Páginas Privacidade e Termos de uso (Google Maps bloqueado): carregam, trazem o aviso "Versão para revisão",
citam a LGPD e o controlador, têm o mesmo cabeçalho e rodapé do site, estão linkadas no rodapé do site
e passam em axe WCAG AA e nos alvos de toque em 375 e 1280 px.
Nada aqui fala com o banco nem cria usuários.
"""

import pytest

from conftest import FEEDBACK_FORM_URL, esperar_lista
from test_07_layout import ALVOS_PEQUENOS
from test_16_interface_medalhas import axe_da_secao

PAGINAS = {
    "privacidade": {"arquivo": "/privacidade.html", "h1": "Política de Privacidade", "outra": "termos"},
    "termos": {"arquivo": "/termos.html", "h1": "Termos de Uso", "outra": "privacidade"},
}
LARGURAS = [(375, 812), (1280, 900)]
IDS = ["375px", "1280px"]
CONTROLADOR = "Grupo Ecotroca, UPx Facens"
EMAIL = "matheusgiachetti1@gmail.com"
# O link das páginas estáticas precisa ser o mesmo FEEDBACK_FORM_URL de js/config.js
FORMULARIO = FEEDBACK_FORM_URL


@pytest.mark.parametrize("nome", PAGINAS)
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_pagina_carrega_com_aviso_de_revisao(abrir, nome, largura, altura):
    info = PAGINAS[nome]
    p = abrir(info["arquivo"], largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    page.wait_for_selector("h1")
    assert page.locator("h1").count() == 1 and page.locator("h1").inner_text() == info["h1"]
    assert page.title().startswith(info["h1"])
    assert page.locator("html").get_attribute("lang") == "pt-BR"

    # Aviso visível, logo no início, e sem se passar por texto jurídico final
    aviso = page.locator(".documento__revisao")
    assert aviso.is_visible() and "Versão para revisão" in aviso.inner_text()
    assert "não foi revisado por um profissional do direito" in aviso.inner_text()
    assert page.evaluate("document.querySelector('.documento__revisao').getBoundingClientRect().top < innerHeight")
    corpo = page.locator("main").inner_text()
    assert "texto jurídico final" not in corpo.lower() or "ainda não" in aviso.inner_text()

    # Controlador e contato (os dados informados pelo grupo)
    assert CONTROLADOR in corpo
    assert page.locator(f'main a[href="mailto:{EMAIL}"]').count() >= 1
    assert page.locator(f'main a[href="{FORMULARIO}"]').count() >= 1  # outra forma de contato
    assert page.locator('main a[href^="tel:"]').count() == 0 and "98181" not in corpo  # sem telefone
    if nome == "privacidade":
        assert "LGPD" in corpo and "13.709/2018" in corpo
        for tema in ("E-mail e senha", "Apelido", "Cidade", "Descartes registrados", "Medalhas", "Sua localização"):
            assert tema in corpo, tema
        assert "não é gravada" in corpo  # a localização não vira coluna do banco
        assert "Excluir minha conta" in corpo

    # Mesmo cabeçalho e rodapé do site
    assert page.locator("header.topo .topo__marca img").is_visible()
    assert page.locator("footer.rodape .rodape__slogan").inner_text() == "O caminho para um futuro sustentável."
    assert "Projeto da UPx · Facens" in page.locator("footer.rodape").inner_text()
    # Rodapé: links para as duas páginas, e o da própria página marcado como atual
    assert page.locator('footer a[href="/privacidade.html"]').count() == 1
    assert page.locator('footer a[href="/termos.html"]').count() == 1
    assert page.locator(f'footer a[aria-current="page"]').inner_text() == ("Privacidade" if nome == "privacidade" else "Termos de uso")

    # Layout, acessibilidade e console
    assert page.evaluate("[document.documentElement.scrollWidth <= innerWidth, getComputedStyle(document.querySelector('.documento')).textAlign]") == [True, "start"]
    assert axe_da_secao(page, "body") == []
    assert page.evaluate(ALVOS_PEQUENOS) == []
    assert p.erros == [], p.erros


@pytest.mark.parametrize("nome", PAGINAS)
def test_paginas_se_ligam_entre_si_e_voltam_ao_site(abrir, nome):
    info = PAGINAS[nome]
    p = abrir(info["arquivo"], largura=1280, altura=900)
    page = p.page
    page.locator(f'footer a[href="{PAGINAS[info["outra"]]["arquivo"]}"]').click()
    page.wait_for_url(f'**{PAGINAS[info["outra"]]["arquivo"]}')
    assert page.locator("h1").inner_text() == PAGINAS[info["outra"]]["h1"]
    page.locator("header a.topo__voltar").click()
    esperar_lista(page)
    assert page.url.rstrip("/").endswith(("5173", "localhost:5173")) or page.locator("#mapa").count() == 1


@pytest.mark.parametrize("nome", PAGINAS)
@pytest.mark.parametrize("largura,altura", LARGURAS, ids=IDS)
def test_rodape_do_site_linka_as_duas_paginas(abrir, nome, largura, altura):
    p = abrir("/", largura=largura, altura=altura, toque=largura < 900)
    page = p.page
    esperar_lista(page)
    link = page.locator(f'footer.rodape a[href="{nome}.html"]')
    assert link.count() == 1 and link.inner_text() == ("Privacidade" if nome == "privacidade" else "Termos de uso")
    link.scroll_into_view_if_needed()
    box = link.bounding_box()
    assert box["height"] >= 44
    link.click()
    page.wait_for_url(f"**/{nome}.html")
    assert page.locator(".documento__revisao").is_visible()
    assert p.erros == [], p.erros


def test_pagina_404_nao_depende_das_novas():
    """As novas páginas são arquivos estáticos na raiz; a Vercel as serve também sem '.html' (cleanUrls)."""
    import json
    from pathlib import Path

    cfg = json.loads((Path(__file__).resolve().parent.parent / "vercel.json").read_text(encoding="utf-8"))
    assert cfg.get("cleanUrls") is True

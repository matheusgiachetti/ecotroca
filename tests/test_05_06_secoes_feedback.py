"""Itens 5 e 6 — seções da página, créditos do Unsplash e botão "Dê sua opinião"."""

import re

from conftest import FEEDBACK_FORM_URL, esperar_lista

SECOES = {
    "inicio": "Início",
    "mapa": "Mapa",
    "como-funciona": "Como funciona",
    "o-que-descartar": "O que descartar",
    "duvidas": "Dúvidas",
    "sobre": "Sobre",
}


def test_secoes_menu_e_rodape(abrir):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    for id_, rotulo in SECOES.items():
        secao = page.locator(f"main section#{id_}")
        assert secao.count() == 1, id_
        titulo = secao.get_attribute("aria-labelledby")
        assert titulo and page.locator(f"#{titulo}").inner_text().strip(), id_
        link = page.locator("#menu-principal a", has_text=rotulo)
        assert link.get_attribute("href") == f"#{id_}"

    assert page.locator("h1").count() == 1
    assert page.locator("footer.rodape").count() == 1
    assert page.locator("details.pergunta").count() >= 5


def test_creditos_do_unsplash(abrir):
    p = abrir("/")
    creditos = p.page.locator(".rodape__creditos")
    texto = re.sub(r"\s+", " ", creditos.inner_text())
    assert "Chris Ried" in texto and "Eugenia Pan'kiv" in texto and "Unsplash" in texto
    hrefs = creditos.locator("a").evaluate_all("els => els.map(a => a.href)")
    assert any(h.startswith("https://unsplash.com/@cdr6934") for h in hrefs)
    assert any(h.startswith("https://unsplash.com/@eugenivy_now") for h in hrefs)
    assert any(re.match(r"^https://unsplash\.com/\?", h) for h in hrefs)
    assert all("utm_source=ecotroca" in h and "utm_medium=referral" in h for h in hrefs)


def test_dê_sua_opinião_abre_o_google_forms(abrir):
    assert FEEDBACK_FORM_URL.startswith("https://docs.google.com/forms/")
    p = abrir("/")
    page = p.page
    esperar_lista(page)
    links = page.locator("[data-feedback-link]")
    assert links.count() == 2
    for i in range(links.count()):
        link = links.nth(i)
        assert link.is_visible()
        assert link.get_attribute("href") == FEEDBACK_FORM_URL
        assert link.get_attribute("target") == "_blank"
        assert "noopener" in (link.get_attribute("rel") or "")
        # Quem usa leitor de tela sabe que abre outra aba
        assert "nova aba" in (link.get_attribute("aria-label") or "")

    with p.contexto.expect_page() as nova:
        links.first.click()
    aba = nova.value
    aba.wait_for_load_state("domcontentloaded")
    assert aba.url.startswith("https://docs.google.com/forms/")
    assert aba.evaluate("window.opener") is None

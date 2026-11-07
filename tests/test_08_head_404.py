"""Item 8 — metadados do <head> e página 404."""

import io
import urllib.error
import urllib.request

import pytest
from PIL import Image

from conftest import BASE_URL, LOCAL, RAIZ
from test_07_layout import ALVOS_PEQUENOS
from test_10_desempenho_a11y import AXE

PRODUCAO = "https://ecotroca-xi.vercel.app"


def _baixar(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.status, resp.headers.get("content-type", ""), resp.read()


def test_head(abrir):
    page = abrir("/").page
    meta = lambda seletor: page.locator(seletor).first.get_attribute("content")  # noqa: E731

    assert page.locator("html").get_attribute("lang") == "pt-BR"
    titulo = page.title()
    assert titulo.startswith("Ecotroca") and 30 <= len(titulo) <= 70, titulo
    descricao = meta("meta[name='description']")
    assert 70 <= len(descricao) <= 160, len(descricao)
    assert "width=device-width" in meta("meta[name='viewport']")
    assert page.locator("link[rel='canonical']").get_attribute("href") == f"{PRODUCAO}/"

    assert meta("meta[property='og:type']") == "website"
    assert meta("meta[property='og:locale']") == "pt_BR"
    assert meta("meta[property='og:title']").startswith("Ecotroca")
    assert meta("meta[property='og:description']")
    assert meta("meta[property='og:url']") == f"{PRODUCAO}/"
    assert meta("meta[property='og:image:alt']")
    assert meta("meta[name='twitter:card']") == "summary_large_image"

    # Imagem de compartilhamento: existe e tem 1200x630
    og = meta("meta[property='og:image']")
    assert og == f"{PRODUCAO}/assets/og.jpg"
    imagem = Image.open(RAIZ / "assets" / "og.jpg")
    assert imagem.size == (1200, 630)
    assert meta("meta[property='og:image:width']") == "1200"
    assert meta("meta[property='og:image:height']") == "630"

    # Ícones respondem
    for seletor in ("link[rel='icon'][sizes='any']", "link[rel='icon'][type='image/png']", "link[rel='apple-touch-icon']"):
        href = page.locator(seletor).get_attribute("href")
        status, tipo, corpo = _baixar(f"{BASE_URL}/{href}")
        assert status == 200 and corpo, href
        Image.open(io.BytesIO(corpo))  # é imagem de verdade


def test_pagina_404(abrir):
    arquivo = RAIZ / "404.html"
    assert arquivo.exists(), "falta 404.html"

    respostas_ruins = []

    def preparar(page):
        page.on("response", lambda r: respostas_ruins.append(f"{r.status} {r.url}")
                if r.status >= 400 and "/nao/existe/" not in r.url and "/pagina-que" not in r.url else None)
        if LOCAL:
            # Simula a Vercel: qualquer caminho inexistente (inclusive aninhado) recebe o 404.html.
            # Isso prova que os caminhos de CSS e imagens são absolutos.
            corpo = arquivo.read_text(encoding="utf-8")
            page.route("**/nao/existe/**",
                       lambda r: r.fulfill(status=404, content_type="text/html; charset=utf-8", body=corpo))

    p = abrir("/nao/existe/pagina", largura=375, preparar=preparar)
    page = p.page
    page.wait_for_load_state("networkidle")

    assert page.locator("html").get_attribute("lang") == "pt-BR"
    assert "404" in page.title() or "não encontrada" in page.title().lower()
    assert page.locator("meta[name='robots']").get_attribute("content").startswith("noindex")
    assert page.locator("h1").count() == 1
    assert page.locator("a[href='/']").count() >= 1
    assert page.locator("a[href='/#mapa']").count() >= 1
    # Usa o CSS do site (fundo off-white e fonte do título do hero)
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(250, 248, 243)"
    assert "Times New Roman" in page.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily")
    assert page.evaluate("document.querySelector('.hero__foto img').naturalWidth") > 0, "foto não carregou"
    assert page.evaluate("[document.documentElement.scrollWidth, innerWidth]") == [375, 375]
    assert page.evaluate(ALVOS_PEQUENOS) == []
    page.add_script_tag(url=AXE)
    violacoes = page.evaluate(
        "async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } }))"
        ".violations.map(v => v.id)"
    )
    assert violacoes == [], violacoes
    # O único "erro" aceito é o próprio status 404 do documento
    erros = [e for e in p.erros if "status of 404" not in e]
    assert respostas_ruins == [] and erros == [], (respostas_ruins, erros)


@pytest.mark.skipif(LOCAL, reason="o status 404 real só existe na Vercel")
def test_status_404_na_vercel():
    with pytest.raises(urllib.error.HTTPError) as erro:
        _baixar(f"{BASE_URL}/pagina-que-nao-existe")
    assert erro.value.code == 404
    assert "Esta página não existe" in erro.value.read().decode()

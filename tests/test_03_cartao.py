"""Item 3 — detalhes do ponto, com dados reais e com dados controlados (telefone, HTML malicioso)."""

import re

from conftest import esperar_lista, esperar_marcadores, responder_supabase

XSS = '<img src=x onerror="window.__xss=1">Ponto <b>teste</b>'
PONTOS_CONTROLADOS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "nome": XSS,
        "endereco": 'Rua Teste, 1 <script>window.__xss=2</script>',
        "latitude": -23.50,
        "longitude": -47.45,
        "horario": "Seg. a sex., 8h às 17h",
        "residuos_aceitos": ["Celulares", "Lâmpadas"],
        "telefone": "(15) 3417-3825",
        "fonte": 'Fonte <a href="javascript:alert(1)">x</a>',
        "verificado": True,
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "nome": "Ponto sem dados opcionais",
        "endereco": "Rua Dois, 2",
        "latitude": -23.51,
        "longitude": -47.46,
        "horario": None,
        "residuos_aceitos": [],
        "telefone": None,
        "fonte": None,
        "verificado": False,
    },
]


def _rotulos(detalhes):
    return [t.strip() for t in detalhes.locator("dt").all_text_contents()]


def test_detalhes_com_dados_reais(abrir, pontos_db):
    p = abrir("/", largura=1280, altura=900, mapa=True)
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, len(pontos_db))
    por_nome = {l["nome"]: l for l in pontos_db}

    for indice in range(page.locator("#lista-pontos .ponto").count()):
        item = page.locator("#lista-pontos .ponto").nth(indice)
        cabeca = item.locator(".ponto__cabeca")
        cabeca.click()
        assert cabeca.get_attribute("aria-expanded") == "true"
        detalhes = item.locator(".ponto__detalhes")
        assert detalhes.is_visible()
        linha = por_nome[item.locator(".ponto__nome").inner_text()]

        assert item.locator(".ponto__endereco").inner_text() == linha["endereco"]
        assert _rotulos(detalhes)[:2] == ["Horário", "Resíduos aceitos"]
        assert linha["horario"] in detalhes.inner_text()
        assert detalhes.locator(".ponto__residuos li").all_text_contents() == linha["residuos_aceitos"]
        esperado_status = "Verificado" if linha["verificado"] else "Em verificação"
        assert detalhes.locator(".status").inner_text() == esperado_status
        assert detalhes.locator(".status__fonte").inner_text() == f"Fonte: {linha['fonte']}"

        rota = detalhes.get_by_role("link", name=re.compile("^Como chegar"))
        href = rota.get_attribute("href")
        lat, lng = map(float, re.search(r"destination=(-?[\d.]+),(-?[\d.]+)$", href).groups())
        assert href.startswith("https://www.google.com/maps/dir/?api=1&destination=")
        assert abs(lat - linha["latitude"]) < 1e-6 and abs(lng - linha["longitude"]) < 1e-6
        assert rota.get_attribute("target") == "_blank" and "noopener" in rota.get_attribute("rel")

        # O balão do mapa abre junto, com o nome do ponto
        page.wait_for_selector(".gm-style-iw", timeout=15000)
        assert linha["nome"] in page.locator(".gm-style-iw-chr, .gm-style-iw").first.inner_text()
    assert p.erros == [], p.erros


def test_telefone_campos_vazios_e_texto_do_banco_escapado(abrir):
    p = abrir("/", largura=1280, altura=900, preparar=responder_supabase(PONTOS_CONTROLADOS), mapa=True)
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, 2)

    item = page.locator("#lista-pontos .ponto").filter(has_text="Rua Teste")
    item.locator(".ponto__cabeca").click()
    detalhes = item.locator(".ponto__detalhes")

    # HTML do banco aparece como texto, nunca vira elemento
    assert item.locator(".ponto__nome").inner_text() == XSS
    assert item.locator("img, b, script").count() == 0
    assert detalhes.locator("a[href^='javascript']").count() == 0
    assert "<a href=" in detalhes.locator(".status__fonte").inner_text()
    page.wait_for_selector(".gm-style-iw", timeout=15000)
    assert page.locator(".gm-style-iw img, .gm-style-iw b, .gm-style-iw script").count() == 0
    assert page.evaluate("window.__xss") is None

    # Telefone vira link tel: só com dígitos
    tel = detalhes.locator("a[href^='tel:']")
    assert tel.inner_text() == "(15) 3417-3825"
    assert tel.get_attribute("href") == "tel:1534173825"
    assert "Telefone" in _rotulos(detalhes)
    assert detalhes.locator(".status").inner_text() == "Verificado"

    # Ponto sem campos opcionais: textos de "não informado", sem telefone
    outro = page.locator("#lista-pontos .ponto").filter(has_text="Ponto sem dados opcionais")
    outro.locator(".ponto__cabeca").click()
    texto = outro.locator(".ponto__detalhes").inner_text()
    assert texto.count("Não informado. Confirme com o local.") == 2
    assert "Telefone" not in _rotulos(outro.locator(".ponto__detalhes"))
    assert "Fonte: não informada" in texto
    assert outro.locator(".status").inner_text() == "Em verificação"
    assert p.erros == [], p.erros

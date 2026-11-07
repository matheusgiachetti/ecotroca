"""Item 2 — "Usar minha localização" (posição emulada pelo navegador de teste)."""

from conftest import esperar_lista, km_do_texto

VILA_HORTENCIA = {"latitude": -23.5036, "longitude": -47.4383}  # ao lado do Ecoponto Vila Hortência
SAO_PAULO = {"latitude": -23.5505, "longitude": -46.6333}       # ~85 km de Sorocaba


def _distancias(page):
    return [km_do_texto(t) for t in page.locator("#lista-pontos .ponto__distancia").all_text_contents()]


def test_permitida_ordena_por_distancia_e_marca_o_mais_proximo(abrir, pontos_db):
    # Permissão já concedida: o site localiza sozinho ao abrir
    p = abrir("/", largura=1280, altura=900, geo=VILA_HORTENCIA, permitir_geo=True)
    page = p.page
    page.wait_for_selector("#lista-pontos .selo--proximo", timeout=25000)

    distancias = _distancias(page)
    assert len(distancias) == len(pontos_db)
    assert distancias == sorted(distancias), distancias

    primeiro = page.locator("#lista-pontos .ponto").first
    assert "is-proximo" in primeiro.get_attribute("class")
    assert primeiro.locator(".selo--proximo").inner_text().strip().lower() == "mais próximo"
    assert page.locator("#lista-pontos .selo--proximo").count() == 1
    assert primeiro.locator(".ponto__nome").inner_text() == "Ecoponto Vila Hortência"

    status = page.locator("#status-localizacao").inner_text()
    assert status.startswith("Mais próximo: Ecoponto Vila Hortência")
    assert "Por enquanto" not in status
    assert "do mais perto ao mais longe" in page.locator("#lista-contagem").inner_text()

    # O mapa também destaca o mais próximo e mostra "Você está aqui"
    page.wait_for_selector("#mapa-google .marcador.is-proximo", timeout=25000)
    assert page.locator("#mapa-google .marcador-usuario").count() == 1
    assert p.erros == [], p.erros


def test_clique_no_botao_localiza(abrir):
    # Permissão concedida só depois de abrir: exige o clique
    p = abrir("/", geo=VILA_HORTENCIA)
    page = p.page
    esperar_lista(page)
    p.contexto.grant_permissions(["geolocation"])
    page.click("#botao-localizacao")
    page.wait_for_selector("#lista-pontos .selo--proximo", timeout=20000)
    assert page.locator("#botao-localizacao span").inner_text() == "Atualizar localização"


def test_negada_mostra_mensagem_amigavel(abrir, pontos_db):
    p = abrir("/", geo=VILA_HORTENCIA, permitir_geo=False)
    page = p.page
    esperar_lista(page)
    page.click("#botao-localizacao")
    status = page.locator("#status-localizacao")
    page.wait_for_function("() => document.querySelector('#status-localizacao').classList.contains('is-erro')",
                           timeout=20000)
    texto = status.inner_text()
    assert texto.startswith("Você não permitiu o acesso à localização. Tudo bem")
    assert status.get_attribute("role") == "status"
    # A lista continua lá, em ordem alfabética, sem distâncias nem selo
    assert page.locator("#lista-pontos .ponto").count() == len(pontos_db)
    assert page.locator("#lista-pontos .selo--proximo").count() == 0
    assert page.locator("#botao-localizacao span").inner_text() == "Usar minha localização"


def test_longe_de_sorocaba_avisa(abrir):
    p = abrir("/", geo=SAO_PAULO, permitir_geo=True)
    page = p.page
    page.wait_for_selector("#lista-pontos .selo--proximo", timeout=25000)
    assert min(_distancias(page)) > 60
    assert "Por enquanto, a Ecotroca mostra pontos de Sorocaba/SP." in page.locator("#status-localizacao").inner_text()

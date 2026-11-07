"""Item 1 — mapa do Google com a chave restrita, pontos vindos do Supabase e aviso de erro sobreposto."""

from conftest import esperar_lista, esperar_marcadores


def test_mapa_carrega_com_pontos_do_supabase(abrir, pontos_db):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)

    # Não está no modo demonstração e a lista é exatamente o que está no banco
    assert page.locator("#aviso-demo").is_hidden()
    nomes_lista = page.locator("#lista-pontos .ponto__nome").all_text_contents()
    assert sorted(nomes_lista) == sorted(l["nome"] for l in pontos_db)

    # O mapa do Google foi desenhado e tem um marcador por ponto
    page.wait_for_selector("#mapa-google .gm-style", timeout=25000)
    esperar_marcadores(page, len(pontos_db))
    assert page.locator("#mapa-google .mapa__aviso").count() == 0, "aviso de erro apareceu com a chave válida"
    assert page.get_by_text("For development purposes only").count() == 0, "Google exige faturamento"
    assert p.erros == [], p.erros


def test_aviso_sobreposto_quando_a_chave_e_recusada(abrir, servidor_porta_errada, pontos_db):
    # Porta fora da lista de referenciadores da chave: o Google recusa (gm_authFailure)
    p = abrir("/", largura=1280, altura=900, base=servidor_porta_errada)
    page = p.page
    aviso = page.locator("#mapa-google .mapa__aviso", has_text="Não foi possível exibir o mapa.")
    aviso.wait_for(timeout=25000)
    assert page.locator("#mapa-google .mapa__aviso").count() == 1  # substituiu o "Carregando o mapa…"

    # Sobreposto: o aviso cobre o container inteiro e é o que está visível no centro dele
    page.evaluate("document.querySelector('#mapa-google').scrollIntoView({ block: 'center', behavior: 'instant' })")
    page.wait_for_timeout(300)
    caixa_mapa = page.locator("#mapa-google").bounding_box()
    caixa_aviso = aviso.bounding_box()
    for chave in ("x", "y", "width", "height"):
        assert abs(caixa_mapa[chave] - caixa_aviso[chave]) < 1.5
    no_centro = page.evaluate(
        """() => { const r = document.querySelector('#mapa-google').getBoundingClientRect();
                   const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                   return !!el && !!el.closest('.mapa__aviso'); }"""
    )
    assert no_centro, "o aviso não está por cima do mapa"

    # A lista continua funcionando
    esperar_lista(page)
    assert page.locator("#lista-pontos .ponto").count() == len(pontos_db)


def test_aviso_quando_o_script_do_maps_nao_baixa(abrir):
    p = abrir("/", preparar=lambda page: page.route("**/maps.googleapis.com/maps/api/js**", lambda r: r.abort()))
    aviso = p.page.locator("#mapa-google .mapa__aviso", has_text="Não foi possível carregar o mapa agora.")
    aviso.wait_for(timeout=25000)
    esperar_lista(p.page)

"""Item 4 — filtros por categoria na lista e nos marcadores; estado vazio."""

from conftest import CATEGORIAS, esperar_lista, esperar_marcadores, responder_supabase
from test_03_cartao import PONTOS_CONTROLADOS


def _clicar_filtro(page, nome):
    botao = page.locator("#filtros .filtro", has_text=nome).first
    botao.click()
    assert botao.get_attribute("aria-pressed") == "true"
    assert page.locator("#filtros .filtro[aria-pressed='true']").count() == 1


def test_filtros_na_lista_e_no_mapa(abrir, pontos_db):
    p = abrir("/", largura=1280, altura=900)
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, len(pontos_db))

    botoes = page.locator("#filtros .filtro").all_text_contents()
    assert botoes[: len(CATEGORIAS) + 1] == ["Todos", *CATEGORIAS]

    for categoria in CATEGORIAS:
        esperados = sorted(l["nome"] for l in pontos_db if categoria in l["residuos_aceitos"])
        _clicar_filtro(page, categoria)
        if not esperados:
            assert page.locator("#lista-pontos .lista__estado").is_visible()
            continue
        assert sorted(page.locator("#lista-pontos .ponto__nome").all_text_contents()) == esperados
        esperar_marcadores(page, len(esperados))
        titulos = page.evaluate(
            "() => [...document.querySelectorAll('#mapa-google gmp-advanced-marker')]"
            ".filter(m => m.querySelector('.marcador')).map(m => m.title)"
        )
        assert sorted(titulos) == esperados, titulos

    _clicar_filtro(page, "Todos")
    esperar_marcadores(page, len(pontos_db))
    assert p.erros == [], p.erros


def test_estado_vazio_e_filtro_extra(abrir):
    p = abrir("/", largura=1280, altura=900, preparar=responder_supabase(PONTOS_CONTROLADOS))
    page = p.page
    esperar_lista(page)
    esperar_marcadores(page, 2)

    # Categoria fora da lista padrão vira filtro extra
    assert page.locator("#filtros .filtro", has_text="Lâmpadas").count() == 1

    _clicar_filtro(page, "Pilhas e baterias")
    vazio = page.locator("#lista-pontos .lista__estado")
    assert vazio.inner_text() == "Nenhum ponto aceita esse tipo de resíduo por enquanto. Tente outro filtro."
    assert page.locator("#lista-contagem").inner_text() == "Nenhum ponto encontrado"
    esperar_marcadores(page, 0)

    _clicar_filtro(page, "Lâmpadas")
    assert page.locator("#lista-pontos .ponto").count() == 1
    esperar_marcadores(page, 1)

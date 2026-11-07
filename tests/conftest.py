"""
Ecotroca — infraestrutura dos testes (Playwright + pytest, sem Node).

Uso:
    python -m http.server 5173            # em outro terminal, na raiz do projeto
    python -m pytest tests                # testa http://localhost:5173
    BASE_URL=https://ecotroca-xi.vercel.app python -m pytest tests   # testa produção

A porta 5173 é obrigatória localmente: é a única liberada na chave do Google Maps.
"""

import functools
import http.server
import json
import os
import re
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5173").rstrip("/")
LOCAL = re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", BASE_URL) is not None

_config = (RAIZ / "js" / "config.js").read_text(encoding="utf-8")


def _const(nome):
    achado = re.search(rf"export const {nome} = '([^']*)'", _config)
    return achado.group(1) if achado else ""


SUPABASE_URL = _const("SUPABASE_URL")
SUPABASE_ANON_KEY = _const("SUPABASE_ANON_KEY")
FEEDBACK_FORM_URL = _const("FEEDBACK_FORM_URL")
CATEGORIAS = [
    "Celulares",
    "Pilhas e baterias",
    "Cabos e carregadores",
    "Computadores e periféricos",
    "Eletrodomésticos pequenos",
]


def supabase_rest(metodo, caminho, corpo=None, cabecalhos=None):
    """Chamada direta à API REST do Supabase com a chave PÚBLICA. Devolve (status, json|texto)."""
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{caminho}", data=dados, method=metodo)
    req.add_header("apikey", SUPABASE_ANON_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_ANON_KEY}")
    req.add_header("Content-Type", "application/json")
    for chave, valor in (cabecalhos or {}).items():
        req.add_header(chave, valor)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            texto = resp.read().decode()
            return resp.status, (json.loads(texto) if texto else None)
    except urllib.error.HTTPError as erro:
        texto = erro.read().decode()
        try:
            return erro.code, json.loads(texto)
        except ValueError:
            return erro.code, texto


@pytest.fixture(scope="session")
def pontos_db():
    """Pontos como estão no banco agora (a fonte da verdade dos testes)."""
    status, linhas = supabase_rest("GET", "pontos_coleta?select=*&order=nome")
    assert status == 200, f"Supabase indisponível ({status}): {linhas}. O projeto pode estar pausado."
    assert linhas, "A tabela pontos_coleta está vazia."
    return linhas


@pytest.fixture(scope="session")
def _pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def navegador(_pw):
    b = _pw.chromium.launch()
    yield b
    b.close()


class Pagina:
    """Página aberta + erros de console coletados."""

    def __init__(self, contexto, page):
        self.contexto = contexto
        self.page = page
        self.erros = []
        page.on("console", lambda m: self.erros.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))


@pytest.fixture
def abrir(navegador):
    """abrir(caminho, largura=..., geo=..., permitir_geo=..., preparar=fn(page), base=...) -> Pagina"""
    abertas = []

    def _abrir(caminho="/", *, largura=390, altura=844, geo=None, permitir_geo=False,
               preparar=None, base=BASE_URL, movimento="no-preference", toque=False):
        contexto = navegador.new_context(
            viewport={"width": largura, "height": altura},
            locale="pt-BR",
            geolocation=geo,
            permissions=["geolocation"] if permitir_geo else [],
            reduced_motion=movimento,
            has_touch=toque,
        )
        page = contexto.new_page()
        pagina = Pagina(contexto, page)
        abertas.append(contexto)
        if preparar:
            preparar(page)
        page.goto(base + caminho, wait_until="domcontentloaded")
        return pagina

    yield _abrir
    for contexto in abertas:
        contexto.close()


@pytest.fixture(scope="session")
def servidor_porta_errada():
    """Serve o site numa porta que NÃO está liberada na chave do Maps (para simular a chave recusada)."""
    if not LOCAL:
        pytest.skip("só faz sentido localmente")
    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    servidor = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Silencioso, directory=str(RAIZ)))
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


def responder_supabase(linhas):
    """Devolve um `preparar` que troca a resposta do Supabase por `linhas` (dados controlados)."""

    def preparar(page):
        def tratar(route):
            cors = {
                "access-control-allow-origin": "*",
                "access-control-allow-headers": "*",
                "access-control-allow-methods": "GET, OPTIONS",
            }
            if route.request.method == "OPTIONS":
                route.fulfill(status=204, headers=cors)
            else:
                route.fulfill(status=200, headers={**cors, "content-type": "application/json"},
                              body=json.dumps(linhas))

        page.route("**/rest/v1/pontos_coleta**", tratar)

    return preparar


def esperar_lista(page, timeout=25000):
    page.wait_for_selector("#lista-pontos .ponto", timeout=timeout)


def esperar_marcadores(page, quantidade, timeout=25000):
    page.wait_for_function(
        "n => document.querySelectorAll('#mapa-google .marcador').length === n", arg=quantidade, timeout=timeout
    )


def km_do_texto(texto):
    """'350 m' -> 0.35 · '1,2 km' -> 1.2 · '23 km' -> 23"""
    texto = texto.strip().replace(" ", " ")
    numero = float(re.sub(r"[^\d,]", "", texto).replace(",", "."))
    return numero / 1000 if texto.endswith(" m") else numero

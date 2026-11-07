"""Item 9 — segurança: chave pública só lê, nada de segredo no repositório, nada de innerHTML."""

import re
import subprocess

from conftest import RAIZ, SUPABASE_ANON_KEY, supabase_rest

ID_INEXISTENTE = "00000000-0000-0000-0000-000000000000"
NEGADO = (401, 403)


def test_chave_publica_le(pontos_db):
    assert len(pontos_db) >= 1


def test_chave_publica_nao_escreve():
    # Insert com nome vazio: mesmo que as permissões falhassem, a constraint impediria gravar algo
    status, corpo = supabase_rest("POST", "pontos_coleta",
                                  {"nome": "", "endereco": "", "latitude": 0, "longitude": 0})
    assert status in NEGADO, (status, corpo)
    assert corpo.get("code") == "42501", corpo  # permission denied

    status, corpo = supabase_rest("PATCH", f"pontos_coleta?id=eq.{ID_INEXISTENTE}", {"nome": "x"})
    assert status in NEGADO, (status, corpo)

    status, corpo = supabase_rest("DELETE", f"pontos_coleta?id=eq.{ID_INEXISTENTE}")
    assert status in NEGADO, (status, corpo)


def test_so_chave_publishable_no_front():
    assert SUPABASE_ANON_KEY.startswith("sb_publishable_")


def _historico():
    return subprocess.run(["git", "log", "--all", "-p", "--no-color"], cwd=RAIZ, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=True).stdout


def test_sem_segredos_no_historico_do_git():
    historico = _historico()
    padroes = {
        "chave secreta do Supabase": r"sb_secret_[A-Za-z0-9_-]{10,}",
        "JWT (service_role/anon legada)": r"eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}",
        "chave privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "token do GitHub": r"gh[pousr]_[A-Za-z0-9]{30,}",
        "token da Vercel/genérico": r"(?i)(vercel|api)[_-]?token\s*[:=]\s*['\"][A-Za-z0-9]{16,}",
        "senha de banco": r"postgres(ql)?://[^:\s]+:[^@\s]+@",
    }
    achados = {nome: re.findall(p, historico) for nome, p in padroes.items()}
    assert not any(achados.values()), achados

    # As únicas chaves que podem aparecer são as públicas que já estão em js/config.js
    google = set(re.findall(r"AIza[0-9A-Za-z_-]{35}", historico))
    assert len(google) <= 1, google


def test_sem_innerhtml_no_codigo():
    proibidos = re.compile(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write|setContent\(\s*[`'\"]")
    for arquivo in (RAIZ / "js").glob("*.js"):
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if linha.strip().startswith("//"):
                continue
            assert not proibidos.search(linha), f"{arquivo.name}:{n}: {linha.strip()}"

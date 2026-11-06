"""QA de persistencia do dicionario EAP usando exclusivamente Turso descartavel.

Nenhuma chamada remota ocorre sem credenciais QA separadas, identificacao do host
de producao e opt-in explicito. O teste NUNCA usa o banco conectado ao Vercel.
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse
from uuid import uuid4

import pytest


def _host(url: str) -> str:
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    if url.startswith("wss://"):
        url = "https://" + url[len("wss://"):]
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("A URL do Turso deve ser HTTPS e possuir hostname.")
    return parsed.hostname.lower()


def validar_alvo_qa(qa_url: str, producao_url: str, confirmacao: str) -> None:
    """Bloqueia qualquer teste que possa alcancar o banco de producao."""
    if confirmacao != "YES_DISPOSABLE_WRITES":
        raise ValueError("Escrita remota exige confirmacao explicita de banco descartavel.")
    if not producao_url:
        raise ValueError("Informe a URL de producao para impedir teste no mesmo host.")
    qa_host, prod_host = _host(qa_url), _host(producao_url)
    if qa_host == prod_host:
        raise ValueError("QA e producao usam o mesmo hostname: escrita bloqueada.")
    if not qa_host.startswith(("qa-", "test-", "sandbox-", "disposable-")):
        raise ValueError("Hostname QA deve iniciar por qa-, test-, sandbox- ou disposable-.")


def test_guard_rejeita_mesmo_banco():
    with pytest.raises(ValueError, match="mesmo hostname"):
        validar_alvo_qa(
            "libsql://qa-obra.turso.io", "https://qa-obra.turso.io",
            "YES_DISPOSABLE_WRITES",
        )


def test_guard_rejeita_host_nao_descartavel():
    with pytest.raises(ValueError, match="Hostname QA"):
        validar_alvo_qa(
            "libsql://eap-producao.turso.io", "libsql://prod-outra.turso.io",
            "YES_DISPOSABLE_WRITES",
        )


def test_guard_rejeita_escrita_sem_optin():
    with pytest.raises(ValueError, match="confirmacao explicita"):
        validar_alvo_qa(
            "libsql://qa-obra.turso.io", "libsql://prod-outra.turso.io", "",
        )


@pytest.mark.remote_turso
def test_dicionario_estruturado_persistencia_remota_turso_qa():
    qa_url = os.environ.get("EAP_QA_TURSO_URL", "")
    qa_token = os.environ.get("EAP_QA_TURSO_TOKEN", "")
    prod_url = os.environ.get("EAP_PROD_TURSO_URL", "")
    confirmacao = os.environ.get("EAP_QA_REMOTE_CONFIRM", "")
    if not qa_url or not qa_token or not prod_url:
        pytest.skip("Turso QA isolado nao configurado; persistencia remota nao homologada.")
    validar_alvo_qa(qa_url, prod_url, confirmacao)

    pid = "qa-eap-dicionario-" + uuid4().hex[:16]
    env = dict(os.environ)
    # Atribuir a conexao somente no processo filho, depois de validar a URL.
    env["TURSO_URL"] = qa_url
    env["TURSO_TOKEN"] = qa_token
    env["EAP_QA_PROJECT_ID"] = pid

    escrita = """
import os, models
pid = os.environ["EAP_QA_PROJECT_ID"]
models.init_db()
assert models.buscar_projeto(pid) is None
models.criar_projeto(project_id=pid, nome="Homologacao EAP QA descartavel")
novo = models.atualizar_nodo("1", {
    "project_id": pid,
    "inclusoes": "Formas e armacao QA",
    "exclusoes": "Pintura QA",
    "criterio_aceitacao": "Inspecao QA aprovada",
})
assert novo["inclusoes"] == "Formas e armacao QA"
assert novo["exclusoes"] == "Pintura QA"
assert novo["criterio_aceitacao"] == "Inspecao QA aprovada"
"""
    leitura = """
import os, models
from schemas import EAPNodeOutput
pid = os.environ["EAP_QA_PROJECT_ID"]
n = models.buscar_por_eap_id("1", pid)
assert n is not None
out = EAPNodeOutput.model_validate(n).model_dump()
assert out["inclusoes"] == "Formas e armacao QA"
assert out["exclusoes"] == "Pintura QA"
assert out["criterio_aceitacao"] == "Inspecao QA aprovada"
"""
    limpeza = """
import os, models
pid = os.environ["EAP_QA_PROJECT_ID"]
if models.buscar_projeto(pid):
    models.deletar_projeto(pid)
assert models.buscar_projeto(pid) is None
"""

    def executar(codigo: str):
        return subprocess.run([sys.executable, "-c", codigo],
                              env=env, text=True, capture_output=True, timeout=120)

    erro = None
    try:
        for etapa, codigo in (("escrita", escrita), ("leitura independente", leitura)):
            resultado = executar(codigo)
            if resultado.returncode:
                erro = f"Falha na etapa {etapa}; verificar logs do runner QA."
                break
    finally:
        resultado_limpeza = executar(limpeza)
        if resultado_limpeza.returncode:
            raise AssertionError("Limpeza do projeto descartavel QA nao confirmada.")
    assert erro is None, erro

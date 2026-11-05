"""Regressão do dicionário estruturado de pacotes EAP (banco isolado)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_dicionario_estruturado_persistencia(tmp_path):
    script = r"""
import os
import models
from pathlib import Path
from schemas import EAPNodeOutput
models.DB_PATH = Path(os.environ["EAP_DB_PATH"])
models.init_db()
pid = "qa-dicionario-estruturado"
models.criar_projeto(project_id=pid, nome="QA Dicionário")
updated = models.atualizar_nodo("1", {"project_id": pid, "inclusoes": "Formas e armação", "exclusoes": "Pintura", "criterio_aceitacao": "Inspeção aprovada"})
out = EAPNodeOutput.model_validate(updated).model_dump()
assert out["inclusoes"] == "Formas e armação"
assert out["exclusoes"] == "Pintura"
assert out["criterio_aceitacao"] == "Inspeção aprovada"
assert models.buscar_por_eap_id("1", pid)["criterio_aceitacao"] == "Inspeção aprovada"
models.init_db()
assert models.buscar_por_eap_id("1", pid)["inclusoes"] == "Formas e armação"
"""
    env = dict(os.environ)
    env.pop("TURSO_URL", None)
    env.pop("TURSO_TOKEN", None)
    env["EAP_DB_PATH"] = str(tmp_path / "qa_eap.db")
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

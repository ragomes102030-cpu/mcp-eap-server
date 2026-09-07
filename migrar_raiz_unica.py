"""F1.2 - migracao para RAZ UNICA por projeto (obra = raiz tipo 'projeto').

Para cada projeto com mais de 1 raiz: cria a raiz da obra (nome vindo dos
metadados, tipo_frente='projeto') e move as raizes antigas para baixo dela,
preservando os ``uid`` e gravando ``eap_id_history`` (via mover_nodo).

Idempotente: projetos ja com 1 unica raiz sao ignorados. Reexecutar e seguro.

Uso (NAO roda em producao sem avaliacao previa):
    python migrar_raiz_unica.py                 # todos os projetos
    python migrar_raiz_unica.py --projetos default
    python migrar_raiz_unica.py --db C:\\tmp\\eap.db
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import models

MOTIVO = "migracao_raiz_unica_F1.2"


def migrar_projeto(models_mod, project_id: str) -> dict:
    nos = models_mod.listar_todos(project_id)
    raizes = [n for n in nos if n.get("parent_id") is None]
    if len(raizes) <= 1:
        return {"project_id": project_id, "status": "skip",
                "raizes": len(raizes)}
    meta = models_mod.buscar_projeto(project_id) or {}
    nome_obra = (meta.get("nome") or project_id).strip()
    eap_obra = models_mod.proximo_eap_id(None, project_id)
    models_mod.inserir_nodo({
        "project_id": project_id, "eap_id": eap_obra, "parent_id": None,
        "nivel": 1, "frente_id": "", "local_id": None,
        "tipo_frente": "projeto", "nome": nome_obra,
        "unidade": None, "quantidade": None,
    })
    movidos = []
    for raiz in raizes:
        res = models_mod.mover_nodo(raiz["eap_id"], eap_obra, project_id,
                                    motivo=MOTIVO)
        movidos.append({"de": raiz["eap_id"], "para": res["eap_id"]})
    return {"project_id": project_id, "status": "migrado",
            "nome_obra": nome_obra, "eap_obra": eap_obra,
            "raizes_originais": len(raizes), "movidos": movidos}


def main() -> None:
    ap = argparse.ArgumentParser(description="Migra projetos para raiz unica (F1.2).")
    ap.add_argument("--db", default=None, help="Caminho do sqlite (default: models.DB_PATH)")
    ap.add_argument("--projetos", nargs="*", default=None,
                    help="Filtrar project_ids (default: todos)")
    args = ap.parse_args()

    if args.db:
        models.DB_PATH = pathlib.Path(args.db)
    models.init_db()

    projetos = args.projetos or [p["project_id"] for p in models.listar_projetos()]
    relatorio = []
    for pid in projetos:
        try:
            relatorio.append(migrar_projeto(models, pid))
        except Exception as exc:  # noqa: BLE001 - relatorio de falha por projeto
            relatorio.append({"project_id": pid, "status": "erro", "erro": str(exc)})
    for linha in relatorio:
        print(linha, flush=True)
    ok = [r for r in relatorio if r["status"] == "migrado"]
    print(f"\n[resumo] migrados={len(ok)} skip={len(relatorio) - len(ok)}",
          flush=True)
    sys.exit(0 if all(r["status"] != "erro" for r in relatorio) else 1)


if __name__ == "__main__":
    main()

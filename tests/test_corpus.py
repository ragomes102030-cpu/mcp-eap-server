"""Corpus sintetico: gerador produz EAPs validas por construcao (0/0)."""
from __future__ import annotations

import random


def test_corpus_pequeno_gera_eap_validas(db):
    import gerador_corpus as g

    rng = random.Random(7)
    pids = []
    for idx in range(1, 9):
        info = g.gerar_projeto(db, rng, idx)
        assert info["total_nos"] > 15
        pids.append(info["project_id"])
    for pid in pids:
        res = db.validar_estrutura(pid)
        assert res["resumo"]["total_problemas"] == 0, pid
        assert res["resumo"]["total_avisos"] == 0, pid
    projetos = db.listar_projetos()
    assert len(projetos) == 8
    # tipos/regioes distribuidas deterministica + metadados de obra
    assert all(p["tipo_obra"] in {"casa", "apartamento", "reforma"}
               for p in projetos)

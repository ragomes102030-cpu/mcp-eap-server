"""F1.3 - dicionario do pacote + dono/OBS + pacotes_sem_dono + SEM_DONO."""
from __future__ import annotations

from conftest import nos_de_teste


def test_atualizar_dicionario_e_dono(db):
    nos_de_teste(db)
    up = db.atualizar_nodo("1.1.1", {
        "project_id": "default",
        "descricao": "Escavacao manual/ mecanizada ate a cota de projeto",
        "criterio_medicao": "Volume escavado; vao/contidos excluidos",
        "responsavel": "Equipe de fundações",
        "disciplina": "civil",
    })
    assert up["descricao"].startswith("Escavacao")
    assert up["responsavel"] == "Equipe de fundações"
    assert up["criterio_medicao"].startswith("Volume")


def test_pacotes_sem_dono_e_aviso_sem_dono(db):
    nos_de_teste(db)  # folha 1.1.1 sem dono
    eids = [n["eap_id"] for n in db.listar_pacotes_sem_dono("default")]
    assert "1.1.1" in eids
    r = db.validar_estrutura("default")
    assert any("SEM_DONO" in a and "'1.1.1'" in a for a in r["avisos"])
    # define dono -> sai do relatorio e do aviso
    db.atualizar_nodo("1.1.1", {"project_id": "default",
                                "responsavel": "Equipe de fundações"})
    assert "1.1.1" not in [
        n["eap_id"] for n in db.listar_pacotes_sem_dono("default")]
    r2 = db.validar_estrutura("default")
    assert not any("SEM_DONO" in a and "'1.1.1'" in a for a in r2["avisos"])

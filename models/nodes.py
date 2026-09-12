"""CRUD de nós da EAP (``eap_node``): árvore, busca, mover, retrabalho e
validação estrutural.

Este é o módulo com mais volume de regra de negócio do pacote — tudo que
opera sobre a hierarquia de nós vive aqui. Depende de ``db`` (conexão/schema)
e ``validacao`` (vocabulário fechado), mas não de ``projetos`` (evita ciclo:
``projetos.criar_projeto`` chama ``inserir_nodo``/``proximo_eap_id`` daqui).
"""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from typing import Any, Iterable

from .db import (
    DEFAULT_PROJECT_ID,
    STRICT_SINGLE_ROOT,
    _agora_iso,
    _chave_ordem,
    _connect,
    _flag,
    _garantir_projeto,
    _gerar_uid,
    _to_dict,
    _to_list,
)
from .validacao import (
    UNIDADE_FILHOS_PERMITIDOS,
    normalizar_tipo_frente,
    normalizar_unidade,
    normalizar_nome_frase,
)


def validar_quantidade_so_em_folha(
    eap_id: str | None,
    quantidade: float | None,
    project_id: str | None = None,
) -> None:
    """Quantidades só em nós-folha. Se tem filhos, quantidade deve ser None."""
    if quantidade is None or quantidade == 0:
        return
    filhos = listar_filhos(eap_id, project_id) if eap_id else []
    if filhos:
        raise ValueError(
            f"Quantidade só permitida em nós-folha. "
            f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
            f"Remova a quantidade ou crie um filho para ela."
        )


def buscar_por_uid(uid: str, project_id: str | None = None) -> dict[str, Any] | None:
    """Retorna um nó pelo ``uid`` estável. Sem projeto, assume o default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    if not uid:
        return None
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE uid = ? AND project_id = ?",
            (uid, pid),
        )
    return _to_dict(cursor.fetchone())


def historico_movimentos(
    project_id: str | None = None,
    uid: str | None = None,
    eap_id_de: str | None = None,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Histórico de renumeracão (EAP_ID display) de nós movidos.

    ``uid`` é estável; ``eap_id`` é display e muda a cada ``move``. A tabela
    permite resolver ``eap_id`` antigo -> nó atual (auditoria / movido_para).
    """
    where: list[str] = []
    params: list[Any] = []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if uid:
        where.append("uid = ?")
        params.append(uid)
    if eap_id_de:
        where.append("eap_id_de = ?")
        params.append(eap_id_de)
    sql = "SELECT * FROM eap_id_history"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limite))
    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
    return _to_list(cursor.fetchall())


def buscar_por_eap_id(
    eap_id: str, project_id: str | None = None
) -> dict[str, Any] | None:
    """Retorna um nó pelo EAP_ID dentro do projeto. Sem projeto, usa o default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE eap_id = ? AND project_id = ?",
            (eap_id, pid),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def listar_filhos(
    parent_id: str, project_id: str | None = None
) -> list[dict[str, Any]]:
    """Retorna os filhos diretos de um nó, ordenados pelo código hierárquico.

    Sem ``project_id`` explícito, assume o projeto default (nunca mistura
    projetos na consulta de subárvore)."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE parent_id = ? AND project_id = ?",
            (parent_id, pid),
        )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def listar_todos(project_id: str | None = None) -> list[dict[str, Any]]:
    """Retorna todos os nós, ordenados pelo código hierárquico. Filtra por project_id se informado."""
    if project_id:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE project_id = ?",
                (project_id,),
            )
    else:
        with _connect() as conn:
            cursor = conn.execute("SELECT * FROM eap_node")
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def listar_pacotes_sem_dono(
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Folhas (itens mensuráveis) ainda sem ``responsavel`` definido (OBS)."""
    todos = listar_todos(project_id)
    sao_pais = {n["parent_id"] for n in todos if n.get("parent_id") is not None}
    folhas = [n for n in todos if n["eap_id"] not in sao_pais]
    sem_dono = [
        n for n in folhas
        if not (n.get("responsavel") or "").strip()
    ]
    sem_dono.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return sem_dono


def resumo_quantitativos(
    project_id: str | None = None,
    tipo_frente: str | None = None,
) -> list[dict[str, Any]]:
    """Agrupa quantitativos por (tipo_frente, unidade) — SÓ folhas, null ignorado.

    Nunca mistura unidades: cada grupo tem uma única unidade (RICS NRM).
    """
    todos = listar_todos(project_id)
    sao_pais = {n["parent_id"] for n in todos if n.get("parent_id") is not None}
    folhas = [n for n in todos if n["eap_id"] not in sao_pais]
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for f in folhas:
        unid = f.get("unidade")
        if not unid:
            continue
        tf = f.get("tipo_frente") or "sem_tipo"
        if tipo_frente and tf != tipo_frente:
            continue
        chave = (tf, unid)
        g = grupos.setdefault(chave, {"tipo_frente": tf, "unidade": unid,
                                      "soma": 0.0, "previsto": 0.0,
                                      "retrabalho": 0.0, "folhas": 0})
        q = f.get("quantidade")
        if q is not None:
            valor = float(q)
            g["soma"] = round(g["soma"] + valor, 6)
            if f.get("status") == "retrabalho":
                g["retrabalho"] = round(g["retrabalho"] + valor, 6)
            else:
                g["previsto"] = round(g["previsto"] + valor, 6)
        g["folhas"] += 1
    return sorted(grupos.values(), key=lambda x: (x["tipo_frente"], x["unidade"]))


def _ultimo_segmento(eap_id: str) -> int:
    """Extrai o último segmento numérico de um código '1.2.3' -> 3."""
    if not eap_id:
        return 0
    match = re.search(r"(\d+)\s*$", eap_id)
    return int(match.group(1)) if match else 0


def proximo_eap_id(parent_id: str | None, project_id: str = DEFAULT_PROJECT_ID) -> str:
    """Gera o próximo EAP_ID hierárquico (sem reutilizar códigos deletados)."""
    if parent_id is None:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT eap_id FROM eap_node WHERE project_id = ?",
                (project_id,),
            )
        rows = cursor.fetchall()
        seq = max((_ultimo_segmento(r["eap_id"]) for r in rows), default=0) + 1
        return str(seq)

    irmaos = listar_filhos(parent_id, project_id)
    if irmaos:
        ultimo = max(_ultimo_segmento(r["eap_id"]) for r in irmaos)
        proximo_irmao = ultimo + 1
    else:
        proximo_irmao = 1
    return f"{parent_id}.{proximo_irmao}"


def inserir_nodo(dados: dict[str, Any]) -> dict[str, Any]:
    """Insere um nó e devolve o registro completo persistido."""
    uid = dados.get("uid") or _gerar_uid()
    unidade = normalizar_unidade(dados.get("unidade"))
    quantidade = dados.get("quantidade")
    project_id = dados.get("project_id", DEFAULT_PROJECT_ID)
    _garantir_projeto(project_id)
    tipo_frente = normalizar_tipo_frente(dados.get("tipo_frente"))

    # Validação referencial: mãe precisa existir no mesmo projeto.
    if dados.get("parent_id") is not None:
        pai = buscar_por_eap_id(dados["parent_id"], project_id)
        if pai is None:
            raise ValueError(
                f"PARENT_ID '{dados['parent_id']}' não existe no projeto '{project_id}'."
            )

    validar_quantidade_so_em_folha(None, quantidade, project_id)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_node (
                uid, eap_id, parent_id, nivel, project_id, frente_id, local_id,
                tipo_frente, nome, unidade, quantidade,
                descricao, criterio_medicao, responsavel, disciplina,
                nao_aplicavel, motivo_na,
                status, revisao, motivo, origem_uid,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid,
                dados["eap_id"],
                dados.get("parent_id"),
                dados["nivel"],
                project_id,
                dados.get("frente_id"),
                dados.get("local_id"),
                tipo_frente,
                dados["nome"],
                unidade,
                quantidade,
                dados.get("descricao"),
                dados.get("criterio_medicao"),
                dados.get("responsavel"),
                dados.get("disciplina"),
                _flag(dados.get("nao_aplicavel")),
                dados.get("motivo_na"),
                dados.get("status"),
                dados.get("revisao"),
                dados.get("motivo"),
                dados.get("origem_uid"),
                _agora_iso(),
                _agora_iso(),
            ),
        )
        conn.commit()
    return buscar_por_eap_id(dados["eap_id"], project_id)  # type: ignore[return-value]


def atualizar_nodo(eap_id: str, dados: dict[str, Any]) -> dict[str, Any]:
    """Atualiza campos de um nó existente."""
    project_id = dados.pop("project_id", DEFAULT_PROJECT_ID)
    existente = buscar_por_eap_id(eap_id, project_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if "unidade" in dados:
        normalizar_unidade(dados.get("unidade"))
    unidade = normalizar_unidade(dados.get("unidade")) if "unidade" in dados else None
    quantidade = dados.get("quantidade") if "quantidade" in dados else None
    if "tipo_frente" in dados:
        dados["tipo_frente"] = normalizar_tipo_frente(dados.get("tipo_frente"))

    validar_quantidade_so_em_folha(eap_id, quantidade, project_id)

    campos = []
    valores = []
    for campo in ["frente_id", "local_id", "tipo_frente", "nome",
                  "descricao", "criterio_medicao", "responsavel", "disciplina",
                  "nao_aplicavel", "motivo_na", "status", "revisao", "motivo",
                  "origem_uid"]:
        if campo in dados:
            campos.append(f"{campo} = ?")
            if campo == "nao_aplicavel":
                valores.append(_flag(dados[campo]))
            else:
                valores.append(dados[campo])
    if unidade is not None:
        campos.append("unidade = ?")
        valores.append(unidade)
    if quantidade is not None:
        campos.append("quantidade = ?")
        valores.append(quantidade)

    if not campos:
        return existente

    campos.append("updated_at = ?")
    valores.append(_agora_iso())
    valores.append(eap_id)

    with _connect() as conn:
        conn.execute(
            f"UPDATE eap_node SET {', '.join(campos)} WHERE eap_id = ? AND project_id = ?",
            tuple(valores[:]) + (project_id,),
        )
        conn.commit()
    return buscar_por_eap_id(eap_id, project_id)  # type: ignore[return-value]


def deletar_nodo(
    eap_id: str,
    cascade: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Deleta um nó. Se cascade=True, deleta todos os descendentes."""
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID
    existente = buscar_por_eap_id(eap_id, project_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if cascade:
        for filho in listar_filhos(eap_id, project_id):
            deletar_nodo(filho["eap_id"], cascade=True, project_id=project_id)
    else:
        filhos = listar_filhos(eap_id, project_id)
        if filhos:
            raise ValueError(
                f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
                f"Use cascade=True para deletar com descendentes."
            )

    with _connect() as conn:
        conn.execute(
            "DELETE FROM eap_node WHERE eap_id = ? AND project_id = ?",
            (eap_id, project_id),
        )
        conn.commit()
    return {"deletado": True, "eap_id": eap_id, "project_id": project_id}


def listar_por_tipo_frente(
    tipo_frente: str,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retorna todos os nós que pertencem a um tipo de frente de serviço.

    Sem ``project_id`` explícito, assume o projeto default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE tipo_frente = ? AND project_id = ?",
            (tipo_frente, pid),
        )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def _chave_busca(texto: Any) -> str:
    """Chave de busca: caixa normalizada e sem acento (§3 do prompt).

    'ESCAVAÇÃO' -> 'escavacao'; 'm³' preserva o sobrescrito (não é acento).
    """
    if texto is None:
        return ""
    t = unicodedata.normalize("NFD", str(texto).strip().lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def buscar_eap_node(
    termo: str,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Busca nós por termo em nome, eap_id, frente_id, local_id e responsavel.

    Substring com acento e caixa ignorados: ``escavacao`` acha
    ``ESCAVAÇÃO SAPATAS`` (§3). Sem ``project_id`` explícito, assume o
    projeto default (nunca cruza projetos). Ordenado por EAP_ID.
    """
    if not (termo or "").strip():
        return []
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    chave = _chave_busca(termo)
    achados = [
        n for n in listar_todos(pid)
        if chave in _chave_busca(n.get("nome"))
        or chave in _chave_busca(n.get("eap_id"))
        or chave in _chave_busca(n.get("frente_id"))
        or chave in _chave_busca(n.get("local_id"))
        or chave in _chave_busca(n.get("responsavel"))
    ]
    achados.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return achados


# ─────────────────────────────────────────────────────────────────────────────
# Árvore e validação
# ─────────────────────────────────────────────────────────────────────────────


def _raizes(project_id: str | None = None) -> list[dict[str, Any]]:
    """Todos os nós sem pai (raízes da EAP), opcionalmente por projeto."""
    if project_id:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE parent_id IS NULL AND project_id = ?",
                (project_id,),
            )
    else:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE parent_id IS NULL"
            )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def montar_arvore(
    eap_id: str | None = None,
    project_id: str | None = None,
    max_profundidade: int | None = None,
) -> list[dict[str, Any]]:
    """Monta a(s) árvore(s) aninhada(s) e retorna uma lista de raízes.

    Cada raiz carrega seus dados + uma chave ``filhos`` com os sub-nós
    (recursivo). Chamado sem ``eap_id`` devolve todas as raízes do projeto;
    com ``eap_id`` devolve a subárvore enraizada nesse nó (1 elemento).

    ``max_profundidade`` limita quantos níveis de filhos são expandidos
    (1 = só a raiz, sem filhos; None = sem limite). Nós cortados pelo limite
    ganham ``truncado=True`` e ``total_descendentes`` no lugar de ``filhos``,
    para evitar respostas gigantes em árvores grandes.

    Performance: busca TODOS os nós do escopo numa única query
    (``listar_todos``) e monta a árvore em memória — evita N+1 (uma query
    por nó) que antes deixava obras com milhares de nós lentas (~1,3s para
    ~2.400 nós; agora é da ordem de dezenas de ms, dominado pelo fetch único).
    Os filhos são indexados por ``(project_id, parent_id)`` em vez de só
    ``parent_id`` — isso também corrige um bug latente: chamar sem
    ``eap_id`` e sem ``project_id`` (varrendo todos os projetos) antes
    montava os filhos de cada raiz olhando só o projeto 'default',
    devolvendo filhos errados (ou vazios) pras demais obras.

    Erros (``ValueError``): nó inexistente ou EAP vazia.
    """
    if eap_id:
        raiz = buscar_por_eap_id(eap_id, project_id)
        if raiz is None:
            raise ValueError(f"EAP_ID '{eap_id}' não encontrado na árvore")
        roots: Iterable[dict[str, Any]] = [raiz]
        scope = raiz.get("project_id") or project_id or DEFAULT_PROJECT_ID
    else:
        roots = _raizes(project_id)
        scope = project_id

    if not roots:
        raise ValueError("A EAP está vazia — nenhum nó para exibir.")

    # Uma única leitura de todo o escopo; a árvore é montada em memória a
    # partir daqui (zero queries adicionais por nó).
    todos = listar_todos(scope)
    filhos_por_pai: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for n in todos:
        filhos_por_pai.setdefault((n["project_id"], n["parent_id"]), []).append(n)
    for lista in filhos_por_pai.values():
        lista.sort(key=lambda n: _chave_ordem(n["eap_id"]))

    def _filhos(nodo: dict[str, Any]) -> list[dict[str, Any]]:
        return filhos_por_pai.get((nodo["project_id"], nodo["eap_id"]), [])

    def _contar_descendentes(nodo: dict[str, Any]) -> int:
        total = 0
        for f in _filhos(nodo):
            total += 1 + _contar_descendentes(f)
        return total

    def _montar(nodo: dict[str, Any], profundidade_atual: int) -> dict[str, Any]:
        no = dict(nodo)
        filhos = _filhos(nodo)
        if max_profundidade is not None and profundidade_atual >= max_profundidade:
            if filhos:
                no["truncado"] = True
                no["total_descendentes"] = _contar_descendentes(nodo)
            no["filhos"] = []
        else:
            no["filhos"] = [_montar(f, profundidade_atual + 1) for f in filhos]
        return no

    return [_montar(r, 1) for r in roots]


def mover_nodo(
    eap_id: str,
    novo_parent_id: str | None,
    project_id: str = DEFAULT_PROJECT_ID,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Move um nó (e sua subárvore) para um novo pai.

    ``uid`` é estável e **nunca muda**: apenas ``EAP_ID``/``NIVEL`` são
    recalculados (display). Cada nó movido ganha um registro em
    ``eap_id_history`` (de/para/motivo). Bloqueia movimento que criaria ciclo.
    """
    no = buscar_por_eap_id(eap_id, project_id)
    if no is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if novo_parent_id is not None:
        pai = buscar_por_eap_id(novo_parent_id, project_id)
        if pai is None:
            raise ValueError(
                f"NOVO_PARENT_ID '{novo_parent_id}' não existe no projeto '{project_id}'."
            )
        if novo_parent_id == eap_id:
            raise ValueError("Não é possível mover um nó para ser filho dele mesmo.")
        descendentes = set(_subarvore_ids(eap_id, project_id)) - {eap_id}
        if novo_parent_id in descendentes:
            raise ValueError(
                f"Não é possível mover '{eap_id}' para '{novo_parent_id}': "
                "isso cria um ciclo (o destino é um descendente do nó)."
            )

    sub = _coletar_subarvore(eap_id, project_id)
    return _executar_move(sub, eap_id, novo_parent_id, project_id, motivo)


def registrar_retrabalho(
    eap_id: str | None = None,
    uid: str | None = None,
    project_id: str | None = None,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Registra retrabalho como IRMÃO R{n} do original (mesmo pai).

    - ``motivo`` é obrigatório;
    - original NUNCA é alterado/apagado (só o ``uid`` linkado via origem_uid);
    - R{n} herda unidade/quantidade do original (custo do retrabalho);
    - R é folha legítima: NÃO viola folha/quantidade, nem conta como duplicidade.
    """
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    if not (motivo or "").strip():
        raise ValueError("motivo é obrigatório para registrar retrabalho.")
    if uid:
        original = buscar_por_uid(uid, pid)
    elif eap_id:
        original = buscar_por_eap_id(eap_id, pid)
    else:
        raise ValueError("Informe 'eap_id' ou 'uid' do nó original.")
    if original is None:
        raise ValueError("Nó original não encontrado no projeto.")
    if original.get("parent_id") is None:
        raise ValueError("Não é possível retrabalhar a raiz da obra.")
    pai = buscar_por_eap_id(original["parent_id"], pid)
    if pai is None:
        raise ValueError("Pai do nó original não encontrado.")

    filhos = listar_filhos(original["parent_id"], pid)
    revisoes = [
        (f.get("revisao") or 0) for f in filhos
        if f.get("origem_uid") == original["uid"] and f.get("status") == "retrabalho"
    ]
    rev = (max(revisoes) + 1) if revisoes else 1
    eap_novo = proximo_eap_id(original["parent_id"], pid)
    inserir_nodo({
        "project_id": pid,
        "eap_id": eap_novo,
        "parent_id": original["parent_id"],
        "nivel": (pai.get("nivel") or 1) + 1,
        "frente_id": original.get("frente_id") or "",
        "local_id": original.get("local_id"),
        "tipo_frente": original.get("tipo_frente") or "",
        "nome": f"R{rev} · {original.get('nome') or ''}".strip(),
        "unidade": original.get("unidade"),
        "quantidade": original.get("quantidade"),
        "responsavel": original.get("responsavel"),
        "status": "retrabalho",
        "revisao": rev,
        "motivo": motivo,
        "origem_uid": original["uid"],
    })
    novo = buscar_por_eap_id(eap_novo, pid)
    return novo if novo is not None else {}


def _subarvore_ids(eap_id: str, project_id: str) -> list[str]:
    """EAP_IDs da subárvore (eu + descendentes), em ordem."""
    ids: list[str] = []

    def _coleta(nid: str) -> None:
        ids.append(nid)
        for f in listar_filhos(nid, project_id):
            _coleta(f["eap_id"])

    _coleta(eap_id)
    return ids


def _coletar_subarvore(
    eap_id: str, project_id: str
) -> list[dict[str, Any]]:
    """Lista de {eap_id, parent_id, nivel, dados} da subárvore."""
    out: list[dict[str, Any]] = []
    raiz = buscar_por_eap_id(eap_id, project_id)
    if raiz is None:
        return out

    # BFS para coletar os nós com seus pais originais
    fila: deque[dict[str, Any]] = deque([raiz])
    while fila:
        n = fila.popleft()
        out.append(
            {
                "eap_id": n["eap_id"],
                "parent_id": n["parent_id"],
                "nivel": n["nivel"],
                "dados": n,
            }
        )
        for f in listar_filhos(n["eap_id"], project_id):
            fila.append(f)
    return out


def _executar_move(
    sub: list[dict[str, Any]],
    eap_id: str,
    novo_parent_id: str | None,
    project_id: str,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Reinsere a subárvore re-numerada sob o novo pai, atomicamente.

    Preserva o ``uid`` de cada nó (referência estável) e grava ``eap_id_history``
    com o mapeamento de/para de cada nó movido (auditoria de renumeração).
    """
    raiz_antigo = eap_id

    # Novo código e nível da raiz movida.
    if novo_parent_id is None:
        tops = [r["eap_id"] for r in _raizes(project_id)]
        seg = max((_ultimo_segmento(s) for s in tops), default=0) + 1
        novo_codigo_raiz = str(seg)
        novo_nivel = 1
    else:
        irmaos = listar_filhos(novo_parent_id, project_id)
        seg = max((_ultimo_segmento(f["eap_id"]) for f in irmaos), default=0) + 1
        novo_codigo_raiz = f"{novo_parent_id}.{seg}"
        pai_alvo = buscar_por_eap_id(novo_parent_id, project_id)
        novo_nivel = (pai_alvo["nivel"] + 1) if pai_alvo else 1

    # Próximos códigos por BFS usando os parent_id antigos.
    novo_id: dict[str, str] = {raiz_antigo: novo_codigo_raiz}
    nivel_novo: dict[str, int] = {raiz_antigo: novo_nivel}
    filhos_por_pai: dict[str, list[dict[str, Any]]] = {}
    for n in sub:
        filhos_por_pai.setdefault(n["parent_id"], []).append(n)
    for k in filhos_por_pai:
        filhos_por_pai[k].sort(key=lambda x: _chave_ordem(x["eap_id"]))

    fila: deque[str] = deque([raiz_antigo])
    while fila:
        atual = fila.popleft()
        novo_pai_cod = novo_id[atual]
        nivel_atual = nivel_novo[atual]
        seq = 0
        for filho in filhos_por_pai.get(atual, []):
            seq += 1
            novo_id[filho["eap_id"]] = (
                f"{novo_pai_cod}.{seq}" if novo_pai_cod else f"{seq}"
            )
            nivel_novo[filho["eap_id"]] = nivel_atual + 1
            fila.append(filho["eap_id"])

    # parent_id novo (por código novo). A raiz movida recebe o ``novo_parent_id``
    # direto; os descendentes recebem o código novo do pai antigo (já mapeado).
    novo_pai_map: dict[str, str | None] = {}
    for n in sub:
        cod = novo_id[n["eap_id"]]
        if cod == novo_codigo_raiz:
            novo_pai_map[cod] = novo_parent_id
        else:
            antigo_pai = n["parent_id"]
            novo_pai_map[cod] = novo_id.get(antigo_pai)

    # Persistência atômica (deletar antigos + reinserir novos + histórico).
    with _connect() as conn:
        conn.execute(
            "DELETE FROM eap_node WHERE project_id = ? AND eap_id IN ({0})".format(
                ",".join("?" for _ in novo_id)
            ),
            (project_id, *novo_id.keys()),
        )
        for n in sub:
            antigo = n["eap_id"]
            dados = n["dados"]
            uid_no = dados.get("uid") or _gerar_uid()
            conn.execute(
                """
                INSERT INTO eap_node (
                    uid, eap_id, parent_id, nivel, project_id, frente_id, local_id,
                    tipo_frente, nome, unidade, quantidade,
                    descricao, criterio_medicao, responsavel, disciplina,
                    nao_aplicavel, motivo_na,
                    status, revisao, motivo, origem_uid,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid_no,
                    novo_id[antigo],
                    novo_pai_map[novo_id[antigo]],
                    nivel_novo[antigo],
                    project_id,
                    dados.get("frente_id"),
                    dados.get("local_id"),
                    dados.get("tipo_frente"),
                    dados["nome"],
                    dados.get("unidade"),
                    dados.get("quantidade"),
                    dados.get("descricao"),
                    dados.get("criterio_medicao"),
                    dados.get("responsavel"),
                    dados.get("disciplina"),
                    _flag(dados.get("nao_aplicavel")),
                    dados.get("motivo_na"),
                    dados.get("status"),
                    dados.get("revisao"),
                    dados.get("motivo"),
                    dados.get("origem_uid"),
                    dados.get("created_at") or _agora_iso(),
                    _agora_iso(),
                ),
            )
            conn.execute(
                "INSERT INTO eap_id_history "
                "(uid, project_id, eap_id_de, eap_id_para, motivo) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid_no, project_id, antigo, novo_id[antigo], motivo),
            )
        conn.commit()

    return {
        "movido": True,
        "eap_id": novo_codigo_raiz,
        "novo_parent_id": novo_pai_map.get(novo_codigo_raiz),
        "nivel": novo_nivel,
        "nos_renumerados": len(sub),
    }


def validar_estrutura(
    project_id: str | None = None,
    *,
    strict_single_root: bool | None = None,
) -> dict[str, Any]:
    """Percorre toda a árvore e reporta problemas de integridade.

    Verifica:
      * duplicidade de EAP_ID (EAP_ID repetido em mais de uma linha);
      * nós órfãos (PARENT_ID aponta para um EAP_ID que não existe);
      * NIVEL inconsistente com a posição real na árvore (pai.nivel + 1);
      * quantidade em nó não-folha (dupla contagem de quantitativos);
      * tipo_frente do filho divergente do pai nos níveis >= 2 (coerência).

    Além dos ``problemas`` (integridade estrutural — invalidam a árvore), devolve
    ``avisos`` semânticos que NÃO invalidam: múltiplas raízes por projeto, nome
    em CAIXA ALTA, agregador carregando unidade de medida e tipo_frente
    divergente já no nível 2. Use ``avisos`` para orientar qualidade sem quebrar
    a auditoria estrutural.
    """
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID
    problemas: list[str] = []
    todos = listar_todos(project_id)

    # 1. Duplicidade de EAP_ID (agora via PK composta, mas mantido para robustez).
    vistos: dict[str, int] = {}
    for n in todos:
        vistos[n["eap_id"]] = vistos.get(n["eap_id"], 0) + 1
    for chave, qtd in vistos.items():
        if qtd > 1:
            problemas.append(f"EAP_ID '{chave}' aparece {qtd} vezes (duplicidade)")

    # 2. Órfãos.
    existentes = set(vistos.keys())
    for n in todos:
        pai = n.get("parent_id")
        if pai is not None and pai not in existentes:
            problemas.append(f"Nó '{n['eap_id']}' é órfão: PARENT_ID '{pai}' não existe")

    # 3. NIVEL inconsistente — percorre a árvore real e confere a profundidade.
    def _percorre(nodo: dict[str, Any], nivel_esperado: int) -> None:
        if nodo["nivel"] != nivel_esperado:
            problemas.append(
                f"Nó '{nodo['eap_id']}' tem NIVEL {nodo['nivel']}, "
                f"mas está na posição {nivel_esperado} da árvore"
            )
        filhos = listar_filhos(nodo["eap_id"], project_id)
        # 4/5 coerência de tipo_frente e quantidade em não-folha (acumuladas aqui)
        if nodo.get("quantidade") is not None and filhos:
            problemas.append(
                f"Nó '{nodo['eap_id']}' tem quantidade {nodo['quantidade']} "
                f"mas não é folha — dupla contagem no quantitativo."
            )
        for filho in filhos:
            if nivel_esperado >= 2 and filho.get("tipo_frente") and nodo.get("tipo_frente"):
                if filho["tipo_frente"] != nodo["tipo_frente"]:
                    problemas.append(
                        f"Filho '{filho['eap_id']}' (tipo {filho['tipo_frente']}) "
                        f"diverge do pai '{nodo['eap_id']}' ({nodo['tipo_frente']})."
                    )
            _percorre(filho, nivel_esperado + 1)

    for raiz in _raizes(project_id):
        _percorre(raiz, 1)

    # ── Avisos semânticos (não invalidam a árvore; orientam qualidade) ──
    avisos: list[str] = []
    raizes = _raizes(project_id)
    _strict = STRICT_SINGLE_ROOT if strict_single_root is None else strict_single_root
    if len(todos) > 0 and len(raizes) != 1:
        _msg_multi = (
            f"MULTI_ROOT: projeto tem {len(raizes)} raízes "
            f"({', '.join(r['eap_id'] for r in raizes)}); "
            "exige 1 raiz (a obra) por projeto."
        )
        if _strict:
            problemas.append(_msg_multi)
        else:
            avisos.append(_msg_multi)
    _UNIDADES_MEDIDA = {"m²", "m³", "ml", "kg"}

    def _semantica(nodo: dict[str, Any], nivel: int) -> None:
        filhos = listar_filhos(nodo["eap_id"], project_id)
        nome = nodo.get("nome") or ""
        if nome.isupper() and any(ch.isalpha() for ch in nome):
            avisos.append(
                f"Nó '{nodo['eap_id']}' com nome em CAIXA ALTA "
                f"({nome[:45]!r}): prefira Capitalização de Frase."
            )
        if filhos and nodo.get("unidade") in _UNIDADES_MEDIDA:
            avisos.append(
                f"Nó '{nodo['eap_id']}' é agregador (tem {len(filhos)} filho(s)) "
                f"mas carrega unidade de medida '{nodo.get('unidade')}': "
                "deixe a unidade para as folhas."
            )
        if not filhos and not (nodo.get("responsavel") or "").strip():
            avisos.append(
                f"SEM_DONO: folha '{nodo['eap_id']}' ('{nome[:40]}') sem responsável."
            )
        if not filhos and nodo.get("quantidade") is None and not nodo.get("nao_aplicavel"):
            avisos.append(
                f"FANTASMA: folha '{nodo['eap_id']}' ('{nome[:40]}') sem quantidade "
                "e sem nao_aplicavel."
            )
        if len(filhos) == 1:
            avisos.append(
                f"FILHO_UNICO: nó '{nodo['eap_id']}' ('{nome[:30]}') com 1 único "
                "filho — decomposição pressupõe ≥ 2."
            )
        _permitidas = UNIDADE_FILHOS_PERMITIDOS.get(nodo.get("unidade"))
        if filhos and _permitidas:
            for filho in filhos:
                if filho.get("unidade") and filho["unidade"] not in _permitidas:
                    avisos.append(
                        f"UNIDADE_INCOMPATIVEL: pai '{nodo['eap_id']}' "
                        f"({nodo.get('unidade')}) com filho '{filho['eap_id']}' "
                        f"({filho['unidade']})."
                    )
        for filho in filhos:
            if (nivel == 1 and filho.get("tipo_frente") and nodo.get("tipo_frente")
                    and nodo.get("tipo_frente") != "projeto"
                    and filho["tipo_frente"] != nodo["tipo_frente"]):
                avisos.append(
                    f"Filho '{filho['eap_id']}' (tipo {filho['tipo_frente']}) diverge "
                    f"do pai '{nodo['eap_id']}' ({nodo['tipo_frente']}) no nível 2."
                )
            _semantica(filho, nivel + 1)

    for raiz in raizes:
        _semantica(raiz, 1)
    avisos.sort()

    return {
        "resumo": {
            "total_nos": len(todos),
            "total_problemas": len(problemas),
            "total_avisos": len(avisos),
            "arvore_valida": len(problemas) == 0,
        },
        "problemas": problemas,
        "avisos": avisos,
    }


def normalizar_nomes_projeto(project_id: str | None = None) -> int:
    """Normaliza nomes CAIXA ALTA de um projeto (uid preservado). Retorna qtd."""
    alterados = 0
    for n in listar_todos(project_id):
        nome = n.get("nome") or ""
        if nome.isupper() and any(c.isalpha() for c in nome):
            novo = normalizar_nome_frase(nome)
            if novo != nome:
                atualizar_nodo(
                    n["eap_id"],
                    {"project_id": project_id or n.get("project_id", DEFAULT_PROJECT_ID),
                     "nome": novo},
                )
                alterados += 1
    return alterados

"""Camada de dados SQLite/libSQL para a EAP (Work Breakdown Structure) de obras.

Pacote dividido por domínio (ver módulos abaixo); este ``__init__`` só
reexporta a API pública para manter compatibilidade com quem importa
``models`` como módulo único (``import models`` / ``models.inserir_nodo(...)``).

Módulos:
  - db: conexão (SQLite local / Turso), schema, migrações
  - validacao: vocabulário fechado e normalização de texto (puro, sem I/O)
  - idempotencia: cache de request_id para as tools de escrita
  - nodes: CRUD de eap_node, árvore, mover, retrabalho, validação estrutural
  - projetos: CRUD de eap_project (metadados de obra)
  - templates: eap_template_real (100+ exemplos reais de EAP por tipo de obra)

Tabelas: eap_node, eap_project, eap_template_real, eap_idempotency,
eap_id_history. Dicionário de unidades válidas: m², m³, ml, un, kg, conj, vb, pt.
Quantidades só são permitidas em nós-folha (sem filhos).
"""

from __future__ import annotations

from .db import (
    DB_PATH,
    DEFAULT_PROJECT_ID,
    SCHEMA,
    STRICT_SINGLE_ROOT,
    init_db,
)
from .idempotencia import (
    limpar_idempotencia_antiga,
    salvar_idempotencia,
    verificar_idempotencia,
)
from .nodes import (
    atualizar_nodo,
    buscar_eap_node,
    buscar_por_eap_id,
    buscar_por_uid,
    deletar_nodo,
    historico_movimentos,
    inserir_nodo,
    listar_filhos,
    listar_pacotes_sem_dono,
    listar_por_tipo_frente,
    listar_todos,
    montar_arvore,
    mover_nodo,
    normalizar_nomes_projeto,
    proximo_eap_id,
    registrar_retrabalho,
    resumo_quantitativos,
    validar_estrutura,
    validar_quantidade_so_em_folha,
)
from .projetos import (
    atualizar_projeto,
    buscar_projeto,
    contar_projetos,
    criar_projeto,
    deletar_projeto,
    listar_projetos,
)
from .templates import (
    contar_templates,
    contar_templates_filtrados,
    inserir_template,
    listar_templates,
)
from .validacao import (
    TIPOS_FRENTE_VALIDOS,
    UNIDADE_FILHOS_PERMITIDOS,
    UNIDADES_VALIDAS,
    normalizar_nome_frase,
    normalizar_tipo_frente,
    normalizar_unidade,
)

__all__ = [
    "DB_PATH", "DEFAULT_PROJECT_ID", "SCHEMA", "STRICT_SINGLE_ROOT", "init_db",
    "limpar_idempotencia_antiga", "salvar_idempotencia", "verificar_idempotencia",
    "atualizar_nodo", "buscar_eap_node", "buscar_por_eap_id", "buscar_por_uid",
    "deletar_nodo", "historico_movimentos", "inserir_nodo", "listar_filhos",
    "listar_pacotes_sem_dono", "listar_por_tipo_frente", "listar_todos",
    "montar_arvore", "mover_nodo", "normalizar_nomes_projeto", "proximo_eap_id",
    "registrar_retrabalho", "resumo_quantitativos", "validar_estrutura",
    "validar_quantidade_so_em_folha",
    "atualizar_projeto", "buscar_projeto", "contar_projetos", "criar_projeto",
    "deletar_projeto", "listar_projetos",
    "contar_templates", "contar_templates_filtrados", "inserir_template",
    "listar_templates",
    "TIPOS_FRENTE_VALIDOS", "UNIDADE_FILHOS_PERMITIDOS", "UNIDADES_VALIDAS",
    "normalizar_nome_frase", "normalizar_tipo_frente", "normalizar_unidade",
]

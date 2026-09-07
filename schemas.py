"""Schemas Pydantic de entrada e saída para o servidor MCP de EAP.

Cada field carrega ``description``/``title`` para gerar bons schemas de input e
de output expostos às ferramentas MCP, auxiliando o modelo a usar as tools.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────


class CriarEAPNodeInput(BaseModel):
    """Campos necessários para criar um nó da EAP.

    ``EAP_ID`` e ``NIVEL`` NÃO entram aqui: são gerados/calculados pelo servidor
    (código hierárquico no formato "1.2.3" e ``pai.nivel + 1``).
    """

    parent_id: Optional[str] = Field(
        default=None,
        title="EAP_ID do pai",
        description="Referência ao nó pai. Nulo/omitido = raiz da EAP.",
        examples=["1.1", None],
    )
    frente_id: str = Field(
        default="",
        title="Frente de serviço",
        description="Identificador da frente de serviço à qual o item pertence.",
        examples=["FR-001"],
    )
    local_id: Optional[str] = Field(
        default=None,
        title="Local / ambiente",
        description="Identificador do local ou ambiente (bloco, pavimento, sala).",
        examples=["BLOCO-A", "P1"],
    )
    tipo_frente: str = Field(
        default="",
        title="Tipo de frente",
        description="Classificação do tipo de serviço, ex.: alvenaria, estrutura, fundacao.",
        examples=["fundacao", "alvenaria"],
    )
    nome: str = Field(
        title="Descrição",
        description="Descrição legível do item da EAP.",
        min_length=1,
        examples=["Sapata S1"],
    )
    unidade: Optional[str] = Field(
        default=None,
        title="Unidade de medida",
        description="Unidade de medida do item (m², m³, un, ml, kg...).",
        examples=["m³", "un"],
    )
    quantidade: Optional[float] = Field(
        default=None,
        ge=0,
        title="Quantidade planejada",
        description="Quantidade planejada do item (>= 0).",
        examples=[120.5],
    )
    nao_aplicavel: Optional[bool] = Field(
        default=None,
        title="Não aplicável",
        description="True = pacote N/A (verba/provisório); folha sem quantidade vira aviso FANTASMA a menos que N/A.",
    )
    motivo_na: Optional[str] = Field(
        default=None,
        title="Motivo N/A",
        description="Justificativa do N/A (ex.: provisório, verba).",
    )

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("nome não pode ser vazio")
        return v.strip()

    model_config = ConfigDict(extra="forbid")


class GetEAPNodeInput(BaseModel):
    """Consulta um nó específico pelo EAP_ID."""

    eap_id: str = Field(
        title="EAP_ID",
        description="Código hierárquico do nó desejado, ex.: '1.2.3'.",
        examples=["1.2.3"],
    )

    model_config = ConfigDict(extra="forbid")


class GetEAPTreeInput(BaseModel):
    """Consulta a árvore da EAP. Se ``eap_id`` for omitido, retorna a árvore toda."""

    eap_id: Optional[str] = Field(
        default=None,
        title="EAP_ID (opcional)",
        description="Se informado, retorna a subárvore enraizada nesse nó; "
        "se vazio/omitido, retorna a EAP inteira em estrutura aninhada.",
        examples=["1", None],
    )

    model_config = ConfigDict(extra="forbid")


class ListarPorTipoFrenteInput(BaseModel):
    """Consulta nós por tipo de frente de serviço."""

    tipo_frente: str = Field(
        title="Tipo de frente",
        description="Tipo de serviço a filtrar, ex.: 'fundacao', 'estrutura'.",
        min_length=1,
        examples=["estrutura"],
    )

    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────


class EAPNodeOutput(BaseModel):
    """Representação de um nó da EAP (sem a subárvore)."""

    eap_id: str = Field(title="EAP_ID", description="Código hierárquico gerado.")
    uid: Optional[str] = Field(
        default=None,
        title="UID",
        description="Referência estável e imutável do nó (não muda em movimentações).",
    )
    descricao: Optional[str] = Field(
        default=None,
        title="Descrição",
        description="Dicionário do pacote: o que está (e não está) incluído.",
    )
    criterio_medicao: Optional[str] = Field(
        default=None,
        title="Critério de medição",
        description="Como medir: vãos descontados, perdas, faixas de medição.",
    )
    responsavel: Optional[str] = Field(
        default=None,
        title="Responsável (OBS)",
        description="Dono do pacote (quem executa/é cobrado).",
    )
    disciplina: Optional[str] = Field(
        default=None,
        title="Disciplina",
        description="Disciplina técnica (civil, elétrica, hidráulica...).",
    )
    nao_aplicavel: Optional[int] = Field(
        default=None,
        title="Não aplicável",
        description="1 = pacote N/A (verba/provisório), 0/None = aplicável.",
    )
    motivo_na: Optional[str] = Field(
        default=None,
        title="Motivo N/A",
        description="Justificativa quando nao_aplicavel=1 (ex.: provisório, verba).",
    )
    parent_id: Optional[str] = Field(
        title="EAP_ID do pai", description="Nulo quando o nó é raiz."
    )
    nivel: int = Field(title="Nível", description="Nível armazenado (pai.nivel + 1).")
    frente_id: str = Field(title="Frente", description="Frente de serviço.")
    local_id: Optional[str] = Field(title="Local", description="Local / ambiente.")
    tipo_frente: str = Field(title="Tipo de frente", description="Tipo de serviço.")
    nome: str = Field(title="Descrição", description="Descrição do item.")
    unidade: Optional[str] = Field(title="Unidade", description="Unidade de medida.")
    quantidade: Optional[float] = Field(
        title="Quantidade", description="Quantidade planejada."
    )

    model_config = ConfigDict(from_attributes=True)


class EAPNodeArvoreOutput(EAPNodeOutput):
    """Nó da EAP que carrega a subárvore aninhada em ``filhos``."""

    filhos: list["EAPNodeArvoreOutput"] = Field(
        default_factory=list,
        title="Filhos",
        description="Sub-nós hierarquicamente dependentes deste nó (recursivo).",
    )


class ArvoreEAPOutput(BaseModel):
    """Envelope de resposta do ``get_eap_tree``: uma lista de raízes aninhadas."""

    raizes: list[EAPNodeArvoreOutput] = Field(
        title="Raízes",
        description="Raiz(es) da EAP. Cada raiz é uma árvore aninhada completa.",
    )

    model_config = ConfigDict(extra="forbid")


class ListarPorTipoFrenteOutput(BaseModel):
    """Envelope de resposta do ``listar_por_tipo_frente``."""

    tipo_frente: str = Field(
        title="Tipo de frente consultado",
        description="Valor de TIPO_FRENTE exatamente como foi solicitado.",
    )
    total: int = Field(
        title="Total de nós",
        description="Quantidade de nós encontrados (0 quando nada corresponde).",
        ge=0,
    )
    nos: list[EAPNodeOutput] = Field(
        title="Nós encontrados",
        description="Nós do tipo de frente solicitado, ordenados por EAP_ID.",
        default_factory=list,
    )

    model_config = ConfigDict(extra="forbid")


class ValidarEstruturaOutput(BaseModel):
    """Resultado da validação de integridade da árvore."""

    resumo: dict = Field(
        title="Resumo",
        description="Totais e flag de validade da árvore.",
    )
    problemas: list[str] = Field(
        default_factory=list,
        title="Problemas",
        description="Lista de mensagens de problemas encontrados.",
    )
    avisos: list[str] = Field(
        default_factory=list,
        title="Avisos",
        description="Lista de avisos semânticos (não invalidam a árvore; orientam qualidade).",
    )

    model_config = ConfigDict(extra="forbid")


class ErroOutput(BaseModel):
    """Resposta estruturada de erro retornada pelo wrapper central."""

    erro: str = Field(
        title="Mensagem de erro",
        description="Descrição do erro ocorrido durante a execução da tool.",
    )

    model_config = ConfigDict(extra="forbid")


class ProjetoOutput(BaseModel):
    """Representação de um projeto (obra) com metadados e contagem de nós."""

    project_id: str = Field(
        title="ID do projeto",
        description="Identificador único do projeto (obra).",
    )
    nome: str = Field(
        title="Nome",
        description="Nome legível da obra.",
    )
    tipo_obra: Optional[str] = Field(
        default=None,
        title="Tipo da obra",
        description="Tipo da obra, ex.: casa, apartamento, reforma.",
    )
    area_m2: Optional[float] = Field(
        default=None,
        title="Área construída",
        description="Área construída em m².",
        ge=0,
    )
    metodo_construtivo: Optional[str] = Field(
        default=None,
        title="Método construtivo",
        description="Método construtivo da obra.",
    )
    regiao: Optional[str] = Field(
        default=None,
        title="Região",
        description="Região do projeto, ex.: sudeste.",
    )
    cliente: Optional[str] = Field(
        default=None,
        title="Cliente",
        description="Cliente ou incorporadora.",
    )
    ativo: int = Field(
        default=1,
        title="Ativo",
        description="1 = ativo; 0 = inativo.",
    )
    total_nos: int = Field(
        default=0,
        title="Total de nós",
        description="Quantidade de nós da EAP deste projeto.",
        ge=0,
    )
    created_at: Optional[str] = Field(
        default=None,
        title="Criado em",
        description="Data de criação (ISO).",
    )
    updated_at: Optional[str] = Field(
        default=None,
        title="Atualizado em",
        description="Data da última atualização (ISO).",
    )

    model_config = ConfigDict(extra="forbid")



"""Typed, stateless input contract for the public and private EAP evidence audit."""
from __future__ import annotations

import math
from typing import Annotated

from pydantic import ConfigDict, Field
from typing_extensions import TypedDict


class DicionarioEapPublico(TypedDict, total=False):
    """Fields accepted inside ``dicionario``/``dictionary`` for a package."""

    __pydantic_config__ = ConfigDict(extra="forbid")

    codigo: Annotated[str | None, Field(description="Código rastreável do pacote.")]
    code: Annotated[str | None, Field(description="Package code (camelCase contract alias).")]
    descricao: Annotated[str | None, Field(description="Descrição do pacote.")]
    unidade: Annotated[str | None, Field(description="Unidade de medição do pacote.")]
    criterio_medicao: Annotated[str | None, Field(description="Regra objetiva de medição.")]
    localizacao: Annotated[str | None, Field(description="Torre, pavimento, ambiente ou frente física.")]
    responsavel: Annotated[str | None, Field(description="Responsável pelo pacote.")]
    responsavelTecnico: Annotated[str | None, Field(description="Responsável pelo pacote (alias camelCase).")]
    criterio_aceitacao: Annotated[str | None, Field(description="Condições objetivas para aceitar a entrega.")]
    criterio_aceite: Annotated[str | None, Field(description="Alias legado de criterio_aceitacao.")]
    acceptanceCriteria: Annotated[str | None, Field(description="Condições objetivas para aceitar a entrega (alias camelCase).")]
    inclusoes: Annotated[str | None, Field(description="Serviços e componentes incluídos.")]
    exclusoes: Annotated[str | None, Field(description="Serviços e componentes excluídos.")]
    disciplina: Annotated[str | None, Field(description="Disciplina técnica.")]
    fonte: Annotated[str | list[str] | None, Field(description="Prancha, revisão, memorial ou registro que sustenta o item.")]
    description: Annotated[str | None, Field(description="Package description (camelCase contract alias).")]
    unit: Annotated[str | None, Field(description="Package unit (camelCase contract alias).")]
    measurementCriterion: Annotated[str | None, Field(description="Measurement rule (camelCase contract alias).")]
    location: Annotated[str | None, Field(description="Physical location (camelCase contract alias).")]
    responsible: Annotated[str | None, Field(description="Package owner (camelCase contract alias).")]
    inclusions: Annotated[str | None, Field(description="Included work (camelCase contract alias).")]
    exclusions: Annotated[str | None, Field(description="Excluded work (camelCase contract alias).")]
    source: Annotated[str | list[str] | None, Field(description="Drawing, revision or record supporting the item (camelCase alias).")]


class ItemEvidenciaEapPublica(TypedDict, total=False):
    """Known fields for one evidence item; all fields stay optional and evidence-based."""

    __pydantic_config__ = ConfigDict(extra="forbid")

    quantidade: Annotated[float | None, Field(strict=True, description="Quantidade planejada comprovada; positiva para cobertura.")]
    plannedQuantity: Annotated[float | None, Field(strict=True, description="Quantidade planejada (alias camelCase de quantidade).")]
    quantity: Annotated[float | None, Field(strict=True, description="Quantidade planejada (alias inglês de quantidade).")]
    produtividade: Annotated[float | None, Field(strict=True, description="Produtividade comprovada; positiva para cobertura.")]
    productivity: Annotated[float | None, Field(strict=True, description="Produtividade (alias camelCase de produtividade).")]
    fonte: Annotated[str | list[str] | None, Field(description="Uma ou mais fontes rastreáveis do item.")]
    source: Annotated[str | list[str] | None, Field(description="Fonte rastreável (alias camelCase).")]
    unidade: Annotated[str | None, Field(description="Unidade da quantidade.")]
    quantityUnit: Annotated[str | None, Field(description="Unidade da quantidade (alias camelCase).")]
    unidade_produtividade: Annotated[str | None, Field(description="Unidade usada para medir produtividade.")]
    productivityUnit: Annotated[str | None, Field(description="Unidade da produtividade (alias camelCase).")]
    responsavel: Annotated[str | None, Field(description="Responsável pelo pacote.")]
    responsible: Annotated[str | None, Field(description="Responsável pelo pacote (alias camelCase).")]
    criterio_aceitacao: Annotated[str | None, Field(description="Condições objetivas para aceitar a entrega do pacote.")]
    criterio_aceite: Annotated[str | None, Field(description="Alias legado de criterio_aceitacao.")]
    acceptanceCriteria: Annotated[str | None, Field(description="Critério de aceite (alias camelCase).")]
    dicionario: Annotated[DicionarioEapPublico | None, Field(description="Dicionário do pacote; dicionario_minimo exige responsavel e criterio_aceitacao dentro ou fora dele.")]
    dictionary: Annotated[DicionarioEapPublico | None, Field(description="Package dictionary (camelCase contract alias).")]


def _first(item: dict, *keys: str):
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _has_text(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_text(part) for part in value)
    return False


def _first_text(*values: object):
    return next((value for value in values if _has_text(value)), None)


def _positive(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (ValueError, TypeError):
        return False


def auditar_cobertura_evidencias(itens: list[dict]) -> dict:
    """Calcula cobertura sem assumir valores ausentes nem acessar banco de dados."""
    total = len(itens)
    def dicionario(item: dict) -> dict:
        nested = _first(item, "dicionario", "dictionary")
        return nested if isinstance(nested, dict) else {}

    checks = {
        "quantidade": sum(_positive(_first(i, "quantidade", "plannedQuantity", "quantity")) for i in itens),
        "produtividade": sum(_positive(_first(i, "produtividade", "productivity")) for i in itens),
        "fonte": sum(_has_text(_first_text(
            _first(i, "fonte", "source"), dicionario(i).get("fonte"), dicionario(i).get("source")
        )) for i in itens),
        "dicionario_minimo": sum(
            _has_text(_first_text(
                _first(i, "responsavel", "responsible"), dicionario(i).get("responsavel"),
                dicionario(i).get("responsavelTecnico"), dicionario(i).get("responsible")
            ))
            and _has_text(_first_text(
                _first(i, "criterio_aceitacao", "criterio_aceite", "acceptanceCriteria"),
                dicionario(i).get("criterio_aceitacao"), dicionario(i).get("criterio_aceite"),
                dicionario(i).get("acceptanceCriteria")
            ))
            for i in itens
        ),
    }
    return {
        "total": total,
        "cobertura": {key: {"preenchidos": count, "total": total} for key, count in checks.items()},
        # An empty payload is not evidence of full coverage (avoid a false green 0/0).
        "lacunas": list(checks) if total == 0 else [key for key, count in checks.items() if count < total],
    }

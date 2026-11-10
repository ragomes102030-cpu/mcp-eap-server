"""Typed, stateless input contract for the public and private EAP evidence audit."""
from __future__ import annotations

import math
import unicodedata
from typing import Annotated

from pydantic import ConfigDict, Field
from typing_extensions import TypedDict

_PENDING_TEXT_MARKERS = {
    "a confirmar", "a definir", "a validar", "na", "n/a", "n.a.",
    "nao aplicavel", "nao declarado", "nao declarada", "nao informado",
    "nao informada", "nao confirmado", "nao confirmada", "nao especificado",
    "nao especificada", "pendente", "sem dado", "sem informacao", "tbd",
    "to be defined", "pending", "unknown", "unspecified",
}
_PENDING_TEXT_PREFIXES = (
    "a confirmar ", "a definir ", "a validar ", "pendente ",
    "sem dado ", "sem informacao ", "nao declarado ", "nao declarada ",
)


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
    discipline: Annotated[str | None, Field(description="Technical discipline (camelCase contract alias).")]
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
    dicionario: Annotated[DicionarioEapPublico | None, Field(description="Dicionário mínimo exige código, descrição, critério de medição, localização e disciplina no dicionário; unidade, responsável e aceite podem estar na raiz ou nele.")]
    dictionary: Annotated[DicionarioEapPublico | None, Field(description="Minimum requires code, description, measurement criterion, location and discipline in the dictionary; unit, owner and acceptance may be at item root or nested.")]


def _first(item: dict, *keys: str):
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _has_text(value: object) -> bool:
    """Treat blank and explicit pending markers as missing evidence."""
    if isinstance(value, str):
        text = value.strip()
        normalized = unicodedata.normalize("NFKD", text)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = " ".join(normalized.casefold().replace("_", " ").replace("-", " ").split())
        return (
            bool(text)
            and normalized not in _PENDING_TEXT_MARKERS
            and not normalized.startswith(_PENDING_TEXT_PREFIXES)
        )
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

    def campo(item: dict, *keys: str):
        nested = dicionario(item)
        return _first_text(
            _first(item, *keys),
            *[nested.get(key) for key in keys],
        )

    def dicionario_minimo_completo(item: dict) -> bool:
        nested = dicionario(item)
        campos = (
            ("codigo", "code"),
            ("descricao", "description"),
            ("criterio_medicao", "measurementCriterion"),
            ("localizacao", "location"),
            ("disciplina", "discipline"),
        )
        return (
            all(_has_text(_first_text(*(nested.get(key) for key in aliases)))
                for aliases in campos)
            and _has_text(campo(item, "unidade", "quantityUnit", "unit"))
            and _has_text(campo(item, "responsavel", "responsavelTecnico", "responsible"))
            and _has_text(campo(item, "criterio_aceitacao", "criterio_aceite", "acceptanceCriteria"))
        )

    def evidencias_presentes(item: dict) -> dict[str, bool]:
        return {
            "quantidade": _positive(_first(item, "quantidade", "plannedQuantity", "quantity")),
            "produtividade": _positive(_first(item, "produtividade", "productivity")),
            "unidade_quantidade": _has_text(campo(item, "unidade", "quantityUnit", "unit")),
            "unidade_produtividade": _has_text(campo(item, "unidade_produtividade", "productivityUnit")),
            "fonte": _has_text(_first_text(
                _first(item, "fonte", "source"),
                dicionario(item).get("fonte"),
                dicionario(item).get("source"),
            )),
            "dicionario_minimo": dicionario_minimo_completo(item),
        }

    detalhes = [evidencias_presentes(item) for item in itens]
    categorias = (
        "quantidade",
        "produtividade",
        "unidade_quantidade",
        "unidade_produtividade",
        "fonte",
        "dicionario_minimo",
    )
    checks = {
        key: sum(item_checks[key] for item_checks in detalhes)
        for key in categorias
    }
    itens_com_lacunas = []
    for index, (item, item_checks) in enumerate(zip(itens, detalhes), start=1):
        lacunas_item = [key for key in categorias if not item_checks[key]]
        if not lacunas_item:
            continue
        nested = dicionario(item)
        codigo = _first_text(
            _first(item, "codigo", "code"),
            nested.get("codigo"),
            nested.get("code"),
        )
        fonte = _first_text(
            _first(item, "fonte", "source"),
            nested.get("fonte"),
            nested.get("source"),
        )
        identificador = _first_text(_first(item, "id", "eap_id", "eapId", "externalId"))
        itens_com_lacunas.append({
            "indice": index,
            "referencia": codigo or identificador or fonte or f"item-{index}",
            "fonte": fonte,
            "lacunas": lacunas_item,
        })
    return {
        "total": total,
        "cobertura": {key: {"preenchidos": count, "total": total} for key, count in checks.items()},
        "itens_com_lacunas": itens_com_lacunas,
        # An empty payload is not evidence of full coverage (avoid a false green 0/0).
        "lacunas": list(checks) if total == 0 else [key for key, count in checks.items() if count < total],
    }

"""Contrato EAP Arquimedes v1: adaptador puro, sem banco e sem dependencia da plataforma.

Nao altera as ferramentas legadas. Validacao estrutural e distinta de auditoria
semantica da regra dos 100%: cobertura nao pode ser presumida apenas da arvore.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

TIPOS = frozenset({"grupo", "pacote", "entrega"})
BASES = frozenset({"project", "deliverable", "system", "discipline", "location", "phase", "component", "other"})

@dataclass(frozen=True)
class EapNodeV1:
    code: str
    parent_code: str | None
    name: str
    node_type: str
    level: int
    description: str | None = None
    inclusions: str | None = None
    exclusions: str | None = None
    responsible: str | None = None
    acceptance_criteria: str | None = None
    decomposition_basis: str | None = None
    location: str | None = None
    unit: str | None = None
    planned_quantity: float | None = None

@dataclass(frozen=True)
class EapContractV1:
    project_ref: str
    version_ref: str
    nodes: tuple[EapNodeV1, ...]
    contract_version: str = "arquimedes.eap.v1"

@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    node_code: str | None
    message: str

@dataclass(frozen=True)
class AuditResult:
    structural_valid: bool
    scope_coverage_verified: bool
    issues: tuple[Issue, ...]

def from_platform_payload(payload: Mapping[str, Any]) -> EapContractV1:
    """Converte formato de intercambio, sem assumir que IDs internos sao estaveis."""
    project_ref = str(payload.get("projectRef") or "").strip()
    version_ref = str(payload.get("versionRef") or "").strip()
    if not project_ref or not version_ref:
        raise ValueError("projectRef e versionRef sao obrigatorios")
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("nodes deve ser lista")
    nodes = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError("cada no deve ser objeto")
        code = str(raw.get("code") or "").strip()
        parent = raw.get("parentCode")
        nodes.append(EapNodeV1(
            code=code, parent_code=None if parent is None else str(parent).strip(),
            name=str(raw.get("name") or "").strip(),
            node_type=str(raw.get("nodeType") or "").strip(),
            level=int(raw.get("level") or 0),
            description=raw.get("description"), inclusions=raw.get("inclusions"),
            exclusions=raw.get("exclusions"), responsible=raw.get("responsible"),
            acceptance_criteria=raw.get("acceptanceCriteria"),
            decomposition_basis=raw.get("decompositionBasis"),
            location=raw.get("location"), unit=raw.get("unit"),
            planned_quantity=raw.get("plannedQuantity"),
        ))
    return EapContractV1(project_ref, version_ref, tuple(nodes))

def audit_contract(contract: EapContractV1) -> AuditResult:
    issues: list[Issue] = []
    def add(code: str, severity: str, node: str | None, message: str) -> None:
        issues.append(Issue(code, severity, node, message))
    if not contract.nodes:
        add("eap_empty", "error", None, "EAP vazia")
    codes: dict[str, EapNodeV1] = {}
    for node in contract.nodes:
        if not node.code or not node.name:
            add("missing_identity", "error", node.code, "Codigo e nome obrigatorios")
        if node.code in codes:
            add("duplicate_code", "error", node.code, "Codigo duplicado na versao")
        codes[node.code] = node
        if node.node_type not in TIPOS:
            add("invalid_type", "error", node.code, "Tipo de no invalido")
        if node.level != len(node.code.split(".")):
            add("invalid_level", "error", node.code, "Nivel difere do codigo")
        if node.decomposition_basis is not None and node.decomposition_basis not in BASES:
            add("invalid_decomposition_basis", "error", node.code, "Criterio de decomposicao invalido")
        if node.planned_quantity is not None and (not isinstance(node.planned_quantity, (int, float)) or node.planned_quantity < 0):
            add("invalid_quantity", "error", node.code, "Quantidade invalida")
    roots = [n for n in contract.nodes if n.parent_code is None]
    if len(roots) != 1:
        add("root_count", "error", None, "EAP deve possuir uma unica raiz")
    for node in contract.nodes:
        if node.parent_code is None:
            continue
        parent = codes.get(node.parent_code)
        if parent is None:
            add("orphan", "error", node.code, "Pai nao encontrado")
            continue
        if parent.node_type != "grupo":
            add("terminal_parent", "error", node.code, "Pacote e entrega nao admitem filhos")
        if not node.code.startswith(parent.code + ".") or node.level != parent.level + 1:
            add("invalid_hierarchy", "error", node.code, "Codigo/nivel nao corresponde ao pai")
        if node.decomposition_basis is None:
            add("decomposition_basis_missing", "warning", node.code, "Criterio de decomposicao nao informado")
    for node in contract.nodes:
        if node.node_type == "grupo" and not any(child.parent_code == node.code for child in contract.nodes):
            add("empty_group", "warning", node.code, "Grupo sem filhos")
    # Nao declarar regra dos 100% atendida sem evidencia verificavel de cobertura.
    add("scope_coverage_not_verified", "warning", None, "Cobertura/exclusividade do escopo requer auditoria semantica e evidencia do projeto")
    return AuditResult(not any(i.severity == "error" for i in issues), False, tuple(issues))

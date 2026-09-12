"""Vocabulário fechado e normalização de texto — sem acesso a banco.

Tudo aqui é função pura (texto -> texto, ou levanta ``ValueError`` pra
valores fora do vocabulário). Não importa ``db`` nem ``nodes``: quem precisa
de validação que depende de dados (ex.: "quantidade só em folha", que precisa
saber se o nó tem filhos) fica em ``nodes.py``, perto do dado que consulta.
"""

from __future__ import annotations

import unicodedata

UNIDADES_VALIDAS = {"m²", "m³", "ml", "un", "kg", "conj", "vb", "pt"}

# F1.5 - matriz unidade pai x unidade filho (RICS NRM). Só soma quem está
# na mesma unidade; 'conj' agrupa 'conj' ou 'un'. Fora disso = UNIDADE_INCOMPATIVEL.
UNIDADE_FILHOS_PERMITIDOS = {
    "conj": {"un", "conj"},
    "m³": {"m³"},
    "m²": {"m²"},
    "ml": {"ml"},
    "un": {"un"},
    "pt": {"pt"},
    "vb": {"vb"},
    "kg": {"kg"},
}

_NORMALIZACAO_UNIDADES = {
    "m2": "m²", "m3": "m³", "m²": "m²", "m³": "m³",
    "ml": "ml", "un": "un", "kg": "kg", "conj": "conj", "vb": "vb", "pt": "pt",
}

# Vocabulário fechado de tipos de frente de serviço (obra real). Mantém a
# classificação estável para consultas e relatórios — o LLM não inventa valores.
TIPOS_FRENTE_VALIDOS = {
    "projeto", "preliminares", "fundacao", "estrutura", "alvenaria",
    "cobertura", "eletrica", "hidrossanitaria", "esquadrias",
    "revestimento", "pintura", "acabamento",
    "infraestrutura", "paisagismo",
}

_NORMALIZACAO_TIPOS = {
    "fundações": "fundacao", "fundacao": "fundacao", "fundacoes": "fundacao",
    "estrutura": "estrutura",
    "alvenaria": "alvenaria", "alvenaria_estrutural": "alvenaria",
    "cobertura": "cobertura", "cubierta": "cobertura", "telhado": "cobertura",
    # F1.2/§3: 'instalacoes' foi DEPRECIADO e dividido em eletrica/hidrossanitaria.
    "eletrica": "eletrica", "eletrico": "eletrica", "elétrica": "eletrica",
    "instalacoes_eletricas": "eletrica",
    "hidrossanitaria": "hidrossanitaria", "hidraulica": "hidrossanitaria",
    "hidraulico": "hidrossanitaria", "hidráulica": "hidrossanitaria",
    "instalacoes_hidrossanitarias": "hidrossanitaria",
    "esgoto": "hidrossanitaria", "agua": "hidrossanitaria", "água": "hidrossanitaria",
    "esquadrias": "esquadrias", "esquinerias": "esquadrias", "esquadria": "esquadrias",
    "revestimento": "revestimento",
    "pintura": "pintura",
    "acabamento": "acabamento",
    "infraestrutura": "infraestrutura", "infra": "infraestrutura",
    "paisagismo": "paisagismo",
    "preliminares": "preliminares", "projeto": "projeto",
}


def normalizar_tipo_frente(tipo: str | None) -> str | None:
    """Normaliza um tipo de frente de serviço pro vocabulário fechado.

    Rejeita valores fora do dicionário em vez de gravar dados sujos.
    Retorna None quando o campo está vazio/ausente.
    """
    if not tipo:
        return None
    t = tipo.strip().lower().replace("_", " ")
    # remove acentos: "Instalações Elétricas" -> "instalacoes eletricas"
    t = "".join(ch for ch in unicodedata.normalize("NFD", t)
                if unicodedata.category(ch) != "Mn").strip()
    # tenta primeiro o valor canônico, depois os sinônimos normalizados
    if t.replace(" ", "_") in TIPOS_FRENTE_VALIDOS:
        return t.replace(" ", "_")
    normalizado = _NORMALIZACAO_TIPOS.get(t) or _NORMALIZACAO_TIPOS.get(t.replace(" ", "_"))
    if normalizado is not None:
        return normalizado
    if t.replace(" ", "_") == "instalacoes":
        raise ValueError(
            "Tipo de frente 'instalacoes' foi DEPRECIADO e dividido em "
            "'eletrica' e 'hidrossanitaria' (informe um deles)."
        )
    raise ValueError(
        f"Tipo de frente '{tipo}' não reconhecido. "
        f"Válidos: {', '.join(sorted(TIPOS_FRENTE_VALIDOS))}"
    )


def normalizar_unidade(unidade: str | None) -> str | None:
    """Normaliza unidade pro dicionário válido. Retorna None se inválida."""
    if not unidade:
        return None
    unidade = unidade.strip().lower()
    normalizada = _NORMALIZACAO_UNIDADES.get(unidade)
    if normalizada is None:
        raise ValueError(
            f"Unidade '{unidade}' não reconhecida. Válidas: {', '.join(sorted(UNIDADES_VALIDAS))}"
        )
    return normalizada


_STOPWORDS_FRASE = {"de", "da", "do", "das", "dos", "e"}


def _palavra_frase(palavra: str) -> str:
    """Capitaliza 'Frase' preservando siglas/numeros compostos (CA-50, BLOCO-A)."""
    import re

    if not palavra:
        return palavra
    if re.search(r"[0-9]|[-/]", palavra) and re.fullmatch(
            r"[A-Z0-9]+(?:[-/][A-Z0-9]+)*", palavra):
        return palavra
    if palavra.lower() in _STOPWORDS_FRASE:
        return palavra.lower()
    return palavra.capitalize()


def normalizar_nome_frase(nome: str | None) -> str | None:
    """Converte nome em CAIXA ALTA para Capitalização de Frase (F1.4).

    Ex.: 'ESCAVAÇÃO SAPATAS' -> 'Escavação Sapatas'; 'AÇO CA-50' mantém 'CA-50'.
    """
    if not nome:
        return nome
    return " ".join(_palavra_frase(p) for p in nome.strip().split())

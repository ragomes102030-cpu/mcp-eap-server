"""Gerador determinístico de corpus de EAPs (projetos/obras) para o MCP EAP.

Produz N projetos com EAP **válida por construção**:
  * 1 raiz por obra (nome Capitalizado, sem tipo_frente para não divergir);
  * fases com tipo_frente coerente pai->filho (sem divergência em nível 2);
  * quantidade apenas em folhas; unidades no vocabulário fechado;
  * nenhum aviso semântico (validar_estrutura -> problemas=0 E avisos=0).

Uso:
    python gerador_corpus.py --projetos 300 --seed 7 --db _corpus.db

NUNCA roda contra o Turso de produção (aborta se TURSO_URL estiver definida).
"""
from __future__ import annotations

import os
import pathlib
import random
import sys

import models

# ── Bloqueio de segurança: nunca gerar contra o banco remoto ──────────────
if os.environ.get("TURSO_URL"):
    raise SystemExit("ERRO: gerador_corpus nao deve rodar com TURSO_URL definida.")

PASTA = pathlib.Path(__file__).resolve().parent

# ── Catalogo sintetico de EAP por fase (valores por 100 m²) ───────────────
FASES = [
    ("Fundações", "fundacao", [
        ("Escavação de sapatas", "m³", 48.0),
        ("Concreto das sapatas", "m³", 12.0),
        ("Aço CA-50 das sapatas", "kg", 700.0),
    ]),
    ("Estrutura", "estrutura", [
        ("Pilares de concreto", "m³", 8.0),
        ("Vigas de concreto", "m³", 14.0),
        ("Laje pré-moldada", "m²", 100.0),
        ("Aço CA-50 da estrutura", "kg", 900.0),
    ]),
    ("Alvenaria", "alvenaria", [
        ("Blocos cerâmicos 9 cm", "m²", 185.0),
        ("Vergas e contravergas", "ml", 40.0),
    ]),
    ("Cobertura", "cobertura", [
        ("Estrutura do telhado", "m²", 125.0),
        ("Telhas cerâmicas", "m²", 125.0),
        ("Cumeeiras e acessórios", "ml", 30.0),
    ]),
    ("Instalações", "instalacoes", [
        ("Pontos elétricos", "pt", 55.0),
        ("Pontos hidráulicos", "pt", 30.0),
        ("Redes de esgoto", "ml", 45.0),
    ]),
    ("Esquadrias", "esquadrias", [
        ("Janelas de alumínio", "un", 11.0),
        ("Portas internas", "un", 12.0),
    ]),
    ("Revestimentos", "revestimento", [
        ("Chapisco", "m²", 350.0),
        ("Reboco", "m²", 350.0),
        ("Contrapiso", "m²", 150.0),
    ]),
    ("Pintura", "pintura", [
        ("Pintura de paredes", "m²", 420.0),
        ("Pintura de tetos", "m²", 150.0),
    ]),
    ("Acabamentos", "acabamento", [
        ("Piso cerâmico", "m²", 120.0),
        ("Paredes de áreas molhadas", "m²", 60.0),
        ("Louças e metais", "conj", 4.0),
    ]),
]

TIPOS = {
    "casa": {"area_min": 60.0, "area_max": 320.0,
             "metodos": ["alvenaria_estrutural", "concreto_armado"]},
    "apartamento": {"area_min": 45.0, "area_max": 180.0,
                    "metodos": ["concreto_armado", "alvenaria_estrutural"]},
    "reforma": {"area_min": 40.0, "area_max": 400.0,
                "metodos": ["alvenaria_estrutural"]},
}
REGIOES = ["norte", "nordeste", "centro_oeste", "sudeste", "sul"]

ADJETIVOS = ["Residencial", "Edifício", "Condomínio", "Vila", "Parque", "Jardim", "Solar", "Portal"]
SUBSTANTIVOS = ["das Flores", "dos Ipês", "do Lago", "Vista Verde", "Alvorada", "do Sol", "das Palmeiras", "Bela Vista", "Santa Clara", "dos Pássaros"]
CLIENTES = ["Construtora Andrade Lima", "MRV Engenharia", "Plaenge", "Cyrela", "Tenda",
            "Construtora Bela Vista", "Incorporadora Horizonte", "Moura Dubeux", "Pessoa Física", "Prefeitura Municipal"]

UNIDADES_DECIMAIS = {"m³", "m²", "ml", "kg"}


def _arredondar_quantidade(q: float, unidade: str) -> float:
    if unidade in UNIDADES_DECIMAIS:
        return round(q, 2)
    return max(1, int(round(q)))


def gerar_projeto(m: "models", rng: random.Random, idx: int) -> dict:
    """Gera 1 obra completa, valida por construcao (0 problemas / 0 avisos)."""
    tipo = rng.choice(list(TIPOS))
    cfg = TIPOS[tipo]
    area = round(rng.uniform(cfg["area_min"], cfg["area_max"]), 1)
    metodo = rng.choice(cfg["metodos"])
    regiao = rng.choice(REGIOES)
    cliente = rng.choice(CLIENTES)
    pid = f"obra-{tipo[:3]}-{idx:04d}"
    nome = f"{rng.choice(ADJETIVOS)} {rng.choice(SUBSTANTIVOS)}"

    m.criar_projeto(pid, nome=nome, tipo_obra=tipo, area_m2=area,
                    metodo_construtivo=metodo, regiao=regiao, cliente=cliente)

    m.inserir_nodo({"project_id": pid, "eap_id": "1", "parent_id": None,
                    "nivel": 1, "frente_id": "", "local_id": None,
                    "tipo_frente": "", "nome": nome,
                    "unidade": None, "quantidade": None})

    total_nos = 1
    num_fase = 0
    for fase_nome, fase_tipo, itens in FASES:
        num_fase += 1
        fase_eap = f"1.{num_fase}"
        m.inserir_nodo({"project_id": pid, "eap_id": fase_eap, "parent_id": "1",
                        "nivel": 2, "frente_id": "", "local_id": None,
                        "tipo_frente": fase_tipo, "nome": fase_nome,
                        "unidade": None, "quantidade": None})
        total_nos += 1
        num_item = 0
        for item_nome, unidade, base in itens:
            num_item += 1
            fator = rng.uniform(0.92, 1.16)
            quantidade = _arredondar_quantidade(base * (area / 100.0) * fator,
                                                unidade)
            m.inserir_nodo({"project_id": pid,
                            "eap_id": f"{fase_eap}.{num_item}",
                            "parent_id": fase_eap, "nivel": 3,
                            "frente_id": "", "local_id": None,
                            "tipo_frente": fase_tipo, "nome": item_nome,
                            "unidade": unidade, "quantidade": quantidade})
            total_nos += 1

    return {"project_id": pid, "tipo_obra": tipo, "area_m2": area,
            "metodo_construtivo": metodo, "regiao": regiao,
            "total_nos": total_nos}


def validar_corpus(m: "models", pids: list[str]) -> dict:
    """Valida TODOS os projetos gerados: exige 0 problemas e 0 avisos."""
    total_nos = 0
    falhas = []
    for pid in pids:
        res = m.validar_estrutura(pid)
        total_nos += res["resumo"]["total_nos"]
        if res["resumo"]["total_problemas"] or res["resumo"]["total_avisos"]:
            falhas.append((pid, res["resumo"]))
    return {"total_nos": total_nos, "falhas": falhas}


def main() -> None:
    args = [a for a in sys.argv[1:]]
    n = 300
    seed = 7
    db_path = pathlib.Path(PASTA) / "_corpus.db"
    if "--projetos" in args:
        n = int(args[args.index("--projetos") + 1])
    if "--seed" in args:
        seed = int(args[args.index("--seed") + 1])
    if "--db" in args:
        db_path = pathlib.Path(args[args.index("--db") + 1])

    if db_path.exists():
        db_path.unlink()
    models.DB_PATH = db_path
    models.init_db()

    rng = random.Random(seed)
    print(f"[corpus] gerando {n} projetos (seed={seed}) em {db_path}", flush=True)
    pids = []
    import time
    inicio = time.perf_counter()
    for idx in range(1, n + 1):
        info = gerar_projeto(models, rng, idx)
        pids.append(info["project_id"])
        if idx in (1, 10, 50, n) or idx % 100 == 0:
            print(f"  ... {idx}/{n} (nos/obra ~{info['total_nos']})", flush=True)
    ger = time.perf_counter() - inicio

    inicio = time.perf_counter()
    resumo = validar_corpus(models, pids)
    val = time.perf_counter() - inicio

    media = resumo["total_nos"] / max(1, n)
    print(f"\n[corpus] geracao: {ger:.1f}s | validacao: {val:.1f}s", flush=True)
    print(f"[corpus] projetos={n} | nos={resumo['total_nos']} | media_nos/obra={media:.1f}",
          flush=True)
    if resumo["falhas"]:
        print(f"[corpus] FALHAS ({len(resumo['falhas'])}): {resumo['falhas'][:5]}",
              flush=True)
        raise SystemExit(1)
    print("[corpus] OK: 0 problemas e 0 avisos em TODOS os projetos.", flush=True)
    lista = models.listar_projetos()
    print(f"[corpus] listar_projetos total_projetos={len(lista)}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()


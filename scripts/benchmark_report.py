"""Persist deterministic pytest/JUnit evidence without guessing outcomes."""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: benchmark_report.py INPUT_JUNIT.xml OUTPUT.json")
    source, target = (Path(x) for x in sys.argv[1:])
    records = []
    totals = {"PASSOU": 0, "FALHOU": 0, "NÃO EXECUTADO": 0, "BLOQUEADO": 0}
    if source.exists():
        tree = ElementTree.parse(source)
        for testcase in tree.iter("testcase"):
            error = testcase.find("error")
            failure = testcase.find("failure")
            skipped = testcase.find("skipped")
            state = "FALHOU" if error is not None or failure is not None else (
                "NÃO EXECUTADO" if skipped is not None else "PASSOU")
            totals[state] += 1
            props = {p.attrib.get("name"): p.attrib.get("value")
                     for p in testcase.findall("./properties/property")}
            records.append({
                "case": testcase.attrib.get("classname", "")+"::"+testcase.attrib.get("name", ""),
                "status": state, "seconds": testcase.attrib.get("time"),
                "expected": props.get("expected"),
                "obtained": props.get("obtained"),
                "difference": props.get("difference"),
                "tolerance": props.get("tolerance"),
                "failure": ((error if error is not None else failure).attrib.get("message","")[:250]
                            if error is not None or failure is not None else None),
            })
    else:
        totals["BLOQUEADO"] = 1
        records.append({"case": "report_missing_junit", "status": "BLOQUEADO"})
    data = {"suite": "Arquimedes Engineering Benchmark",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "commit": os.getenv("GITHUB_SHA", "LOCAL-UNVERIFIED"),
            "repository": os.getenv("GITHUB_REPOSITORY", "LOCAL"),
            "test_environment": "sqlite-temp or in-memory; never production databases",
            "totals": totals, "cases": records,
            "comparison": "References and numeric tolerances are executable assertions in tests/test_arquimedes_engineering_benchmark.py"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"suite": data["suite"],"commit":data["commit"],"totals":totals}, ensure_ascii=False))

if __name__ == "__main__":
    main()

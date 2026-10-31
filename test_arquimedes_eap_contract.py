"""Testes de contrato sem acesso a Turso, MCP ou Plataforma Obras."""
import unittest
from dataclasses import replace
from arquimedes_eap_contract import EapContractV1, EapNodeV1, audit_contract, from_platform_payload

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.root = EapNodeV1("1", None, "Obra", "grupo", 1)
        self.leaf = EapNodeV1("1.1", "1", "Fundacao", "pacote", 2, decomposition_basis="discipline")

    def test_valid_structure_does_not_claim_100_percent(self):
        result = audit_contract(EapContractV1("obra-1", "v1", (self.root, self.leaf)))
        self.assertTrue(result.structural_valid)
        self.assertFalse(result.scope_coverage_verified)
        self.assertIn("scope_coverage_not_verified", [i.code for i in result.issues])

    def test_multiple_roots_blocked(self):
        second = EapNodeV1("2", None, "Outra raiz", "pacote", 1)
        self.assertFalse(audit_contract(EapContractV1("obra-1", "v1", (self.root, second))).structural_valid)

    def test_terminal_cannot_have_children(self):
        parent = replace(self.root, node_type="entrega")
        result = audit_contract(EapContractV1("obra-1", "v1", (parent, self.leaf)))
        self.assertIn("terminal_parent", [i.code for i in result.issues])

    def test_orphan_blocked(self):
        result = audit_contract(EapContractV1("obra-1", "v1", (self.root, replace(self.leaf, parent_code="9"))))
        self.assertIn("orphan", [i.code for i in result.issues])

    def test_payload_requires_version(self):
        with self.assertRaises(ValueError):
            from_platform_payload({"projectRef": "obra", "nodes": []})

    def test_variable_depth(self):
        group = replace(self.leaf, node_type="grupo")
        child = EapNodeV1("1.1.1", "1.1", "Escavacao", "pacote", 3, decomposition_basis="component")
        self.assertTrue(audit_contract(EapContractV1("obra", "v2", (self.root, group, child))).structural_valid)

if __name__ == "__main__":
    unittest.main()

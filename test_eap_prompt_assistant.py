import unittest
from eap_prompt_assistant import propor_eap

class Tests(unittest.TestCase):
    def test_valid(self):
        r = propor_eap('Casa terrea', [{'nome': 'Fundacoes', 'pacotes': [{'nome': 'Escavacao'}]}])
        self.assertTrue(r['ok'])
        self.assertFalse(r['persistido'])
        self.assertFalse(r['regra_100_verificada'])
        self.assertEqual(len(r['proposta']['nodes']), 3)

    def test_missing_packages(self):
        with self.assertRaises(ValueError):
            propor_eap('Casa', [{'nome': 'Fundacoes', 'pacotes': []}])

    def test_negative_quantity(self):
        r = propor_eap('Casa', [{'nome': 'Fundacoes', 'pacotes': [{'nome': 'Sapata', 'quantidade': -1}]}])
        self.assertFalse(r['ok'])

if __name__ == '__main__':
    unittest.main()

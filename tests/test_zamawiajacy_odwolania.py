import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock

from odwolania.extraction import DocumentExtractor
from odwolania.pipeline import DocumentPipeline
from odwolania.rules import empty_result
from odwolania.templates import DocumentTemplate


WZORZEC = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "odwolanie.jsonc"
TEKST = """ODWOŁANIE
Zamawiający (wspólnie prowadzący postępowanie):
1) Zamawiający – Lider:
Miasto Nowe
ul. Miejska 1, 00-112 Nowe
NIP: 0000000001, REGON: 000000001
2) Zamawiający – Partner:
Gmina Lipowa
ul. Klonowa 2, 00-111 Lipowa
NIP: 0000000002, REGON: 000000002
Odwołujący: Konsorcjum wykonawców"""


class TestZamawiajacy(TestCase):
    def test_instrukcja_i_wynik_modelu_dla_zamawiajacych(self):
        wzorzec = DocumentTemplate.load(WZORZEC)
        wynik = empty_result(wzorzec.shape)
        wzorzec.apply_rules(TEKST, wynik)
        self.assertEqual(wynik["Zamawiajacy"], [])

        osoba = {"nazwa": "[PODMIOT_1]", "krs": None, "nip": None, "regon": None, "prowadzacy_postepowanie": 1}
        wynik["Zamawiajacy"] = [osoba]
        klient = Mock()
        klient.complete.return_value = json.dumps(wynik)
        pipeline = DocumentPipeline(None, None, DocumentExtractor(klient))
        dokument = TEKST.replace("Miasto Nowe", "[PODMIOT_1]").replace("Gmina Lipowa", "[PODMIOT_2]")
        mapa = {"[PODMIOT_1]": "Miasto Nowe", "[PODMIOT_2]": "Gmina Lipowa"}
        otrzymany = pipeline._extract(TEKST, dokument, mapa, wzorzec)
        self.assertEqual(otrzymany["Zamawiajacy"], [{**osoba, "nazwa": "Miasto Nowe"}])

        klient.complete.assert_called_once()
        prompt, tekst_wejsciowy = klient.complete.call_args.args
        self.assertEqual(tekst_wejsciowy, dokument)
        self.assertIn("każdego wymienionego zamawiającego", prompt)
        self.assertIn("lidera, jak i wszystkich partnerów", prompt)
        self.assertIn("1 dla wskazanego prowadzącego", prompt)
        self.assertIn("0 dla pozostałych", prompt)

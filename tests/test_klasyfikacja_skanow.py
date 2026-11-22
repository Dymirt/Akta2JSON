from pathlib import Path
from unittest import TestCase

from odwolania.templates import TemplateRegistry


class KlasyfikacjaSkanow(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = TemplateRegistry.load(Path(__file__).resolve().parents[1] / "oczekiwane-json")

    def test_naglowek_odwolania_z_artefaktem_ocr(self):
        template = self.registry.classify("Prezes Krajowej Izby Odwoławczej\n* ODWOŁANIE")
        self.assertEqual(template.name, "odwolanie")

    def test_bankowe_wydruki_bez_naglowka_potwierdzenie(self):
        headers = (
            "Typ zlecenia  Przelew krajowy",
            "z * Przelew z rachunku Szczegóły transakcji",
            "Przelew z rachunku: Szczegóły transakcji",
            "Typ przelewu | Przelęw złotowy na rachunek obcy, elixir",
            "PRZELEW ELIXIR - ONLINE -17,00 PLN",
            "Data operacji . PRZELEW ELIKIR - ONLINE -10 000.00 PLN",
        )
        for header in headers:
            with self.subTest(header=header):
                template = self.registry.classify(f"Bank\n{header}\nRachunek odbiorcy:")
                self.assertEqual(template.name, "przelew")

    def test_wzmianki_o_przelewie_i_odwolaniu_w_innym_dokumencie(self):
        for text in (
            "Ogłoszenie o zamówieniu\nWykonawca wnosi odwołanie do Krajowej Izby Odwoławczej.",
            "Warunki płatności\nPrzelew krajowy\nKwota\nRachunek odbiorcy",
            "Oferta\nZałącznik nr 2: Potwierdzenie przelewu",
            "Instrukcja bankowa\nWybierz typ zlecenia Przelew krajowy",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.registry.classify(text))

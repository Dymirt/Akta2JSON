from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from odwolania.templates import DocumentTemplate


TEKST = (
    "Pełnomocnictwo\nFirma Alfa\nsp. z o.o., ul. Brzozowa 8, 01-234 Nowe Miasto, KRS 0000000001, "
    "NIP 0123456789 (dalej: „Mocodawca”), udziela pełnomocnictwa.\n"
    "Zamawiający: Firma Beta S.A., ul. Długa 1, 98-765 Nowe Miasto."
)


class TestNazwaMocodawcy(TestCase):
    def setUp(self):
        plik = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "pelnomocnictwo.jsonc"
        self.regula = DocumentTemplate.load(plik).rule
        self.dane = {"nazwa": "Firma Alfa sp. z o.o., ul. Brzozowa 8, 01-234 Nowe Miasto",
                     "krs": "0000000001", "nip": "0123456789"}

    def test_przepisuje_nazwe_bez_adresu_z_deklaracji_tego_samego_mocodawcy(self):
        wynik = {"mocodawca": [{"data": deepcopy(self.dane)}]}
        self.regula(TEKST, wynik)
        self.assertEqual(wynik["mocodawca"][0]["data"], {**self.dane, "nazwa": "Firma Alfa sp. z o.o."})

    def test_zachowuje_wynik_ai_bez_jednoznacznej_tozsamosci_danej_spolki(self):
        for tekst, rekordy in (
            (TEKST, [{**self.dane, "nip": "1111111111"}]),
            (TEKST, [{**self.dane, "krs": None}]),
            (TEKST, [{**self.dane, "nazwa": self.dane["nazwa"].replace("Brzozowa", "Krótka")}]),
            (TEKST, [self.dane, {"nazwa": "Firma Beta S.A."}]),
            (TEKST.replace("Mocodawca", "Zamawiający"), [self.dane]),
            (TEKST + '\nFirma Beta S.A. (dalej: „Mocodawca”)', [self.dane]),
            (TEKST.replace("Pełnomocnictwo\n", "Pełnomocnictwo\nW imieniu "), [self.dane]),
        ):
            with self.subTest(tekst=tekst, rekordy=rekordy):
                wynik = {"mocodawca": [{"data": deepcopy(dane)} for dane in rekordy]}
                przed = deepcopy(wynik)
                self.regula(tekst, wynik)
                self.assertEqual(wynik, przed)

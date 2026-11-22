import unittest
from pathlib import Path
from runpy import run_path


REGULA = run_path(str(Path(__file__).resolve().parents[1] / "oczekiwane-json/odwolanie.py"))["odwolanie"]


class KancelariaOdwolujacegoTest(unittest.TestCase):
    def nazwa_po_regule(self, blok, nazwa="Kancelaria Radcy Prawnego"):
        osoba = {"nazwa": nazwa, "imie_nazwisko": "Anna Nowak", "mail": None}
        wynik = {"Odwolujacy": [{"pelnomocnik": osoba}]}
        REGULA.zastosuj("Odwołujący: Firma A\n" + blok, wynik)
        return osoba["nazwa"]

    def test_odtwarza_pelny_wiersz_rubryki_kontaktowej(self):
        firma = "Kancelaria Radcy Prawnego Anna Nowak"
        for etykieta in ("adres do korespondencji:", "radca prawny Anna Nowak"):
            with self.subTest(etykieta=etykieta):
                blok = f"{etykieta}\n. {firma}\nul. Leśna 1\nZamawiający: Gmina"
                self.assertEqual(self.nazwa_po_regule(blok), firma)

    def test_nie_przejmuje_obcej_kancelarii_ani_niejednoznacznego_wiersza(self):
        rubryka = "adres do korespondencji:\nKancelaria Radcy Prawnego Anna Nowak\nul. Leśna 1"
        for blok in ("Zamawiający: Gmina\n" + rubryka,
                     rubryka + "\n" + rubryka.replace("Anna Nowak", "Jan Nowak"),
                     rubryka.replace("ul. Leśna 1", "Przedmiot zamówienia"),
                     rubryka.replace("Anna Nowak\n", "Anna Nowak | e-mail: biuro@example.org\n")):
            with self.subTest(blok=blok):
                self.assertEqual(self.nazwa_po_regule(blok), "Kancelaria Radcy Prawnego")
        self.assertEqual(self.nazwa_po_regule(rubryka, "Inna kancelaria"), "Inna kancelaria")

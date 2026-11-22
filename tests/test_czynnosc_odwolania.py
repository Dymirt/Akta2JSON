from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from odwolania.templates import DocumentTemplate


def odwolanie(punkt, zarzut):
    return (
        "ODWOŁANIE\nZaskarżam czynności Zamawiającego, polegające na:\n"
        f"1) {punkt};\n2) wyborze innej oferty;\n"
        f"Zarzut nr 1 – {zarzut}, tj. naruszenie przepisów ustawy;\n"
        "Zarzut nr 2 – zaniechania odrzucenia oferty, tj. naruszenie przepisów ustawy."
    )


def odwolanie_z_deklaracja(zdarzenie, tytul="naruszenia zasady równego traktowania", tresc="Uzasadnienie faktyczne."):
    return (
        "ODWOŁANIE\nDziałając w imieniu wykonawcy, wnoszę o:\n"
        f"Zamawiający w dniu 4 marca 2026 roku {zdarzenie}.\nZarzut nr 1 {tytul}:\n1.1. {tresc}\n"
        "Zarzut nr 2 – inny zarzut:\n2.1. Odwołujący kwestionuje wybór oferty."
    )


class TestPierwszaCzynnosc(TestCase):
    def setUp(self):
        plik = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "odwolanie.jsonc"
        self.regula = DocumentTemplate.load(plik).rule
        self.wynik = {"OdwolanieKIO": {
            "czynnosc_powod_id": None, "czynnosc_opis": None, "data": "2026-03-20", "czynnosc_dzien": "2026-03-10",
        }}

    def test_granice_pierwszego_przedmiotu_odwolania_na_skanie(self):
        def lista(pierwszy):
            return ("ODWOŁANIE\nNa podstawie ustawy wnoszę odwołanie wobec:\n"
                    f"Stopka kancelarii\n\nl. {pierwszy};\n2. modyfikacji treści SWZ z 19.03.2026;")

        self.wynik["OdwolanieKIO"]["czynnosc_dzien"] = None
        for pierwszy, dzien in (
            ("projektowanych postanowień umowy (PPU), opublikowanych w dniu 14.03.2026 r.", "2026-03-14"),
            ("projektowanych postanowień umowy, przewidujących odbiór w dniu 14.03.2026 r.", None),
            ("projektowanych postanowień umowy, których projekt z 01.03.2026 opublikowano 14.03.2026", None),
        ):
            with self.subTest(pierwszy=pierwszy):
                wynik = deepcopy(self.wynik)
                self.regula(lista(pierwszy), wynik)
                self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_powod_id"], 12)
                self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_opis"], "Projektowane postanowienia umowy")
                self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_dzien"], dzien)
        tekst = lista("modyfikacji treści SWZ")
        for niejednoznaczny in (
            tekst.replace("l. ", "4. "), tekst.replace("wnoszę", "nie wnoszę"),
            "Wzór odwołania\n" + tekst, tekst + "\n" + tekst,
            lista("zaniechania wykluczenia wykonawcy oraz odrzucenia oferty"),
        ):
            with self.subTest(niejednoznaczny=niejednoznaczny):
                wynik = deepcopy(self.wynik)
                self.regula(niejednoznaczny, wynik)
                self.assertEqual(wynik, self.wynik)

    def test_kod_i_opis_wynikaja_z_tego_samego_jednoznacznego_zarzutu(self):
        for punkt, zarzut, kod, opis in (
            ("odrzuceniu oferty", "bezzasadnego odrzucenia oferty", 1, "Decyzja o odrzuceniu oferty"),
            ("wykluczeniu wykonawcy", "bezpodstawnego wykluczenia wykonawcy", 3, "Decyzja o wykluczeniu wykonawcy"),
            ("modyfikacji treści SWZ", "wadliwej modyfikacji treści SWZ", 5, "Modyfikacja treści SWZ"),
            ("zaniechaniu odrzucenia oferty", "zaniechania odrzucenia oferty", 7, "Zaniechanie odrzucenia oferty"),
            ("zaniechaniu wykluczenia wykonawcy", "zaniechania wykluczenia wykonawcy", 8, "Zaniechanie wykluczenia wykonawcy"),
            ("unieważnieniu postępowania", "bezpodstawnego unieważnienia postępowania", 9, "Decyzja o unieważnieniu postępowania"),
            ("zaniechaniu unieważnienia postępowania", "zaniechania unieważnienia postępowania", 10, "Zaniechanie unieważnienia postępowania"),
        ):
            with self.subTest(kod=kod):
                wynik = deepcopy(self.wynik)
                self.regula(odwolanie(punkt, zarzut), wynik)
                self.assertEqual(wynik["OdwolanieKIO"], {
                    **self.wynik["OdwolanieKIO"], "czynnosc_powod_id": kod, "czynnosc_opis": opis,
                })

    def test_zachowuje_wynik_modelu_przy_braku_lub_sprzecznosci_dowodow(self):
        pierwszy = "odrzuceniu oferty"
        tytul = "odrzucenia oferty"
        zgodny = odwolanie(pierwszy, tytul)
        self.wynik["OdwolanieKIO"].update(czynnosc_powod_id=4, czynnosc_opis="Opis z ekstrakcji")
        for tekst in (
            odwolanie("zaniechaniu odrzucenia oferty", tytul),
            odwolanie(pierwszy, "zaniechania odrzucenia oferty"),
            odwolanie(pierwszy, "zaniechania wezwania do wyjaśnień"),
            odwolanie(pierwszy + " oraz wykluczeniu wykonawcy", tytul),
            odwolanie(pierwszy, tytul + " w wyniku wykluczenia wykonawcy"),
            zgodny.replace("Zarzut nr 2", "Zarzut nr 1"),
            zgodny.replace("czynności Zamawiającego", "przykłady innych spraw"),
            "Zamawiający odrzucił ofertę.\nZarzut nr 1 – odrzucenia oferty, tj. naruszenie prawa.",
        ):
            with self.subTest(tekst=tekst):
                wynik = deepcopy(self.wynik)
                self.regula(tekst, wynik)
                self.assertEqual(wynik, self.wynik)

    def test_rozpoznaje_zdarzenie_z_pojedynczej_deklaracji_przed_pierwszym_zarzutem(self):
        for zdarzenie, kod, opis in (
            ("poinformował o odrzuceniu oferty", 1, "Decyzja o odrzuceniu oferty"),
            ("ogłosił wybór najkorzystniejszej oferty", 2, "Ogłoszenie wyboru oferty"),
            ("poinformował o wykluczeniu z postępowania wykonawcy", 3, "Decyzja o wykluczeniu wykonawcy"),
            ("opublikował SWZ", 4, "Publikacja specyfikacji warunków zamówienia (SWZ)"),
            ("zmodyfikował treść SWZ", 5, "Modyfikacja treści SWZ"),
            ("przekazał wykonawcom odpowiedzi i wyjaśnienia do treści SWZ", 6, "Odpowiedzi/wyjaśnienia do SWZ"),
            ("nie odrzucił oferty", 7, "Zaniechanie odrzucenia oferty"),
            ("nie wykluczył z postępowania wykonawcy", 8, "Zaniechanie wykluczenia wykonawcy"),
            ("unieważnił postępowanie", 9, "Decyzja o unieważnieniu postępowania"),
            ("zaniechał unieważnienia postępowania", 10, "Zaniechanie unieważnienia postępowania"),
            ("udostępnił opis przedmiotu zamówienia", 11, "Opis przedmiotu zamówienia (OPZ)"),
        ):
            with self.subTest(zdarzenie=zdarzenie):
                wynik = deepcopy(self.wynik)
                self.regula(odwolanie_z_deklaracja(zdarzenie), wynik)
                self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_powod_id"], kod)
                self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_opis"], opis)

    def test_deklaracja_odstepuje_przy_konkurencyjnym_zarzucie_lub_niejednoznacznym_zdarzeniu(self):
        zdarzenie = "unieważnił postępowanie"
        for tekst in (
            odwolanie_z_deklaracja(zdarzenie, "bezpodstawnego odrzucenia oferty"),
            odwolanie_z_deklaracja(zdarzenie, "naruszenia zasady równości przez odrzucenie oferty"),
            odwolanie_z_deklaracja(zdarzenie, tresc="Przedmiotem pierwszego zarzutu jest wyłącznie odrzucenie oferty."),
            odwolanie_z_deklaracja(zdarzenie, tresc="Opis naruszenia.\nUzasadnienie pierwszego zarzutu:\n"
                                                    "Odwołujący kwestionuje odrzucenie oferty."),
            odwolanie_z_deklaracja(zdarzenie, tresc="Zamawiający bezprawnie wykluczył wykonawcę."),
            odwolanie_z_deklaracja(zdarzenie + " lub opublikował ogłoszenie"),
            odwolanie_z_deklaracja(zdarzenie + " w poprzednim przetargu"),
            odwolanie_z_deklaracja("zamierzał unieważnić postępowanie"),
        ):
            with self.subTest(tekst=tekst):
                wynik = deepcopy(self.wynik)
                self.regula(tekst, wynik)
                self.assertEqual(wynik, self.wynik)

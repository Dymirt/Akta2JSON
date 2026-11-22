import unittest
from copy import deepcopy
from pathlib import Path
from runpy import run_path

from odwolania.templates import DocumentTemplate


WZORZEC = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "przelew.jsonc"
REGULA = run_path(str(WZORZEC.with_suffix(".py")))["przelew"]


class RegulyPrzelewuTest(unittest.TestCase):
    def setUp(self):
        self.wynik = DocumentTemplate.load(WZORZEC).shape
        self.dane = self.wynik["przelew_bankowy"]

    def test_pusta_etykieta_nie_przejmuje_wartosci_sasiedniego_pola(self):
        tekst = (
            "Numer referencyjny:\nKwota: 125,00 PLN\n"
            "Rachunek nadawcy:\nNa rachunek: PL00 1234 5678 9012 3456 7890 1234\n"
            "Data wydruku: 15.06.2026"
        )
        przed = self.dane.copy()
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane, {**przed, "kwota": 125, "na_rachunek": "PL00123456789012345678901234"})

    def test_rachunek_zachowuje_prefiks_i_litery_z_dokumentu(self):
        for zapis, oczekiwany in (
            ("PL\n00 1234 5678 9012 3456 7890 1234", "PL00123456789012345678901234"),
            ("00 1234 5678 9012 3456 7890 1234", "00123456789012345678901234"),
            ("DE89\u00a03704 0044 0532 0130 00", "DE89370400440532013000"),
            ("GB82 WEST\n1234 5698 7654 32", "GB82WEST12345698765432"),
        ):
            with self.subTest(zapis=zapis):
                self.dane["na_rachunek"] = None
                REGULA.zastosuj(f"Na rachunek: {zapis}\nDane banku", self.wynik)
                self.assertEqual(self.dane["na_rachunek"], oczekiwany)

    def test_fragment_iban_nie_przejmuje_nazwy_banku(self):
        self.dane["na_rachunek"] = None
        REGULA.zastosuj("Na rachunek: GB82 WEST 1234\nBANK\nOpis: opłata", self.wynik)
        self.assertIsNone(self.dane["na_rachunek"])

    def test_waluta_kwoty_musi_byc_jednoznaczna(self):
        for tekst in (
            "Kwota: 200,10",
            "Kwota: 200,10 EUR\nOpłata: 0,00 PLN",
            "Kwota: 200,10 PLN\nWaluta: EUR",
            "Kwota: 200,10\nWaluta: PLN\nWaluta: USD",
        ):
            with self.subTest(tekst=tekst):
                przed = deepcopy(self.wynik)
                REGULA.zastosuj(tekst, self.wynik)
                self.assertEqual(self.wynik, przed)
        REGULA.zastosuj("Kwota: 1 200,10\nWaluta: PLN", self.wynik)
        self.assertEqual(self.dane["kwota"], 1200.10)

    def test_numer_transakcji_z_doprecyzowaniem_operacji(self):
        REGULA.zastosuj("Numer transakcji operacji: CEN2611091860728.", self.wynik)
        self.assertEqual(self.dane["numer_transakcji"], "CEN2611091860728")

    def test_rachunki_w_kolumnie_odczytanej_po_etykietach_stron(self):
        tekst = ("Dane\nnadawcy\nDane .\nodbiorcy\nTyp przelewu | Przelew złotowy\n"
                 "02 1090 1505 1725 7418 7044 8046\nFirma A\n"
                 "19 1030 1508 7429 5633 9378 8811\nUrząd Miasta\n")
        przed = self.dane.copy()
        REGULA.zastosuj(tekst + "01 1222 3333 4444 5555 6666 7777\nBank\n", self.wynik)
        self.assertEqual(self.dane, przed)
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane["z_rachunku"], "02109015051725741870448046")
        self.assertEqual(self.dane["na_rachunek"], "19103015087429563393788811")

    def test_rozbity_rachunek_i_dwie_rozne_daty(self):
        self.dane["data_operacji"] = None
        tekst = (
            "Z rachunku:\n0012 3456 7890\n1234 5678 9012\n"
            "Data operacji: 12.01.2026\nData wykonania: 13.01.2026"
        )
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane["z_rachunku"], "001234567890123456789012")
        self.assertIsNone(self.dane["data_operacji"])

    def test_nieprawidlowa_data_i_niedomkniety_cudzyslow(self):
        przed = deepcopy(self.wynik)
        REGULA.zastosuj("Opis: „Faktura 25/08\nData operacji: 31.02.2026", self.wynik)
        self.assertEqual(self.wynik, przed)

    def test_kompletny_rachunek_z_dodatkowym_wierszem_cyfr(self):
        numer = "0000 1111 2222 3333 4444 5555"
        self.dane["na_rachunek"] = None
        REGULA.zastosuj(f"Rachunek odbiorcy: {numer}\n12", self.wynik)
        self.assertIsNone(self.dane["na_rachunek"])
        REGULA.zastosuj(f"Rachunek odbiorcy: {numer}\f12", self.wynik)
        self.assertIsNone(self.dane["na_rachunek"])
        REGULA.zastosuj(f"Rachunek odbiorcy: {numer}1\n2", self.wynik)
        self.assertEqual(self.dane["na_rachunek"], numer.replace(" ", "") + "12")

    def test_kompletny_iban_na_koncu_strony(self):
        REGULA.zastosuj("Z rachunku: GB82 WEST 1234 5698 7654 32\f12", self.wynik)
        self.assertEqual(self.dane["z_rachunku"], "GB82WEST12345698765432")
        self.dane["z_rachunku"] = None
        REGULA.zastosuj("Z rachunku: GB82 WEST 1234\f5698 7654 32", self.wynik)
        self.assertIsNone(self.dane["z_rachunku"])

    def test_tytul_wymaga_jednego_cytatu_na_jednej_stronie(self):
        for tekst in (
            "Tytuł: „Usługa\nKomunikat banku: „Zaksięgowano”",
            "Tytuł: „Usługa\fInformacja dla klienta”",
            "Tytuł:\f„Tekst na następnej stronie”",
        ):
            with self.subTest(tekst=tekst):
                przed = self.dane["tytul"]
                REGULA.zastosuj(tekst, self.wynik)
                self.assertEqual(self.dane["tytul"], przed)
        REGULA.zastosuj("Tytuł: „Faktura\nza kwiecień”.\fInformacja dla klienta", self.wynik)
        self.assertEqual(self.dane["tytul"], "Faktura za kwiecień")

    def test_cytowany_tytul_bez_dwukropka(self):
        REGULA.zastosuj("Tytuł przelewu „Faktura nr 12”.", self.wynik)
        self.assertEqual(self.dane["tytul"], "Faktura nr 12")

    def test_tytul_zawiera_tylko_numer_wydrukowany_wewnatrz_pola(self):
        for tresc, oczekiwany in (
            ("Tytuł:\nOpłata za usługę\nAB/12/26 TR-998", "Opłata za usługę AB/12/26 TR-998"),
            ("Tytuł przelewu: Opłata za usługę", "Opłata za usługę"),
        ):
            with self.subTest(tresc=tresc):
                self.dane["tytul"] = None
                REGULA.zastosuj(tresc + "\nNr ref. ........ TR-998", self.wynik)
                self.assertEqual(self.dane["tytul"], oczekiwany)

    def test_niejednoznaczna_granica_tytulu_pozostawia_wynik_modelu(self):
        self.dane["tytul"] = "Wartość z modelu"
        for tekst in (
            "Tytuł: Dostawa\nTR-998",  # Brak etykiety kończącej pole.
            "Numer transakcji: TR-998\nTytuł: Dostawa\nAB-111\nKwota: 2 PLN",
            "Tytuł: Dostawa\nOpłata bankowa: TR-998\nNr ref.: TR-998",
            "Tytuł: Dostawa\nopłata bankowa 2 PLN\nTR-998\nNr ref.: TR-998",
            "Tytuł: Dostawa\nInny identyfikator\nTR-998\nNr ref.: TR-998",
            "Tytuł: Dostawa\fTR-998\nNr ref.: TR-998",
            "Tytuł:\nStatus: Wykonano\nNr ref.: TR-998",
            "Tytuł: Dostawa\nTR-998\nOpis: Druga wartość\nNr ref.: TR-998",
        ):
            with self.subTest(tekst=tekst):
                REGULA.zastosuj(tekst, self.wynik)
                self.assertEqual(self.dane["tytul"], "Wartość z modelu")

    def test_rozne_struktury_wyniku_zachowuja_swoje_pola(self):
        for wynik in ({}, {"przelew_bankowy": []}, {"przelew_bankowy": {"kwota": {}}}):
            with self.subTest(wynik=wynik):
                przed = deepcopy(wynik)
                REGULA.zastosuj("Kwota: 2,00 PLN\nData realizacji: 01.02.2026", wynik)
                self.assertEqual(wynik, przed)

    def test_kolumny_tabeli_przelewu_odczytane_przez_ocr(self):
        tekst = (
            "Opis\nOpłata skarbowa AB/12/26\n"
            "Kwota Data transakcji Numer referencyjny transakcji\n34,00 PLN 20.05.2026 * REF102\n"
            "Dane nadawcy\nNazwa i adres Numer rachunku Nazwa banku\n"
            "Firma, ul. Letnia 1 PL 00 0011 2233 4455 6677 8899 0012 Bank\n"
            "Dane odbiorcy\nNazwa i adres Numer rachunku\n"
            "Urząd Miasta 12 1090 1090 1000 0000 9999 9999"
        )
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane, {
            "kwota": 34, "data_operacji": "2026-05-20", "numer_transakcji": "REF102",
            "tytul": "Opłata skarbowa AB/12/26",
            "z_rachunku": "PL00001122334455667788990012", "na_rachunek": "12109010901000000099999999",
        })

    def test_zagraniczny_iban_w_tabeli_konczy_sie_przed_nazwa_banku(self):
        REGULA.zastosuj(
            "Dane odbiorcy\nNazwa i adres Numer rachunku Nazwa banku\n"
            "Urząd, GB82 WEST 1234 5698 7654 32 Bank A", self.wynik,
        )
        self.assertEqual(self.dane["na_rachunek"], "GB82WEST12345698765432")

    def test_dwa_rachunki_w_jednej_kolumnie_wymagaja_rozstrzygniecia(self):
        self.dane["z_rachunku"] = None
        REGULA.zastosuj(
            "Dane nadawcy\nNazwa i adres Numer rachunku\nFirma, 00112233445566778899001122\n"
            "Oddział, 99112233445566778899001122\nDane odbiorcy",
            self.wynik,
        )
        self.assertIsNone(self.dane["z_rachunku"])

    def test_kwota_obciazenia_i_etykiety_przelamane_w_komorce(self):
        tekst = (
            "Opis Kwota\nPRZELEW INTERNETOWY -17,00 PLN\nData 2026-04-20\nwykonania\n"
            "Numer 00112\ntransakcji"
        )
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane["kwota"], 17)
        self.assertEqual(self.dane["data_operacji"], "2026-04-20")
        self.assertEqual(self.dane["numer_transakcji"], "00112")

    def test_wiersz_wyciagu_laczy_date_z_rachunkiem_sasiedniej_kolumny(self):
        tekst = (
            "Data Opis Kwota\nData operacji . PRZELEW ELIXIR - ONLINE -120,00 PLN\n"
            "2026-03-17 Z rachunku: 00 1111 1111 2222 2222 3333 3333\n"
            "Data księgowania Nazwa nadawcy\n2026-03-18 Na rachunek: 44 5555 5555 6666 6666 7777 7777"
        )
        REGULA.zastosuj(tekst, self.wynik)
        self.assertEqual(self.dane["kwota"], 120)
        self.assertEqual(self.dane["data_operacji"], "2026-03-17")
        self.assertEqual(self.dane["z_rachunku"], "00111111112222222233333333")
        self.assertEqual(self.dane["na_rachunek"], "44555555556666666677777777")

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from odwolania.templates import DocumentTemplate


WZORZEC = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "pelnomocnictwo.jsonc"
TEKST = """PEŁNOMOCNICTWO
§ 1. Mocodawca
Mocodawcą jest Firma Alfa S.A., ul. Lipowa 1
KRS 0000000001, NIP 0123456789
§ 2. Pełnomocnik
Jan Nowak
Zamawiający: Firma Beta S.A., NIP 9876543210
Podpisy:
Anna Kowalska
"""


class TestRegulyPelnomocnictwa(TestCase):
    def setUp(self):
        self.regula = DocumentTemplate.load(WZORZEC).rule
        self.dane = {"nazwa": "Firma Alfa S.A.", "krs": None, "nip": None, "typ": None}
        self.wynik = {"mocodawca": [{"data": self.dane}]}

    def test_odtwarzanie_osoby_z_funkcja_lub_numerem_wpisu(self):
        mocodawca = "Anna Nowak-Kowalska — Prokurent"
        podpis = "Halina Baran — Prezes Zarządu"
        pelnomocnik = "Mateusz Wierzbicki — adwokat, nr wpisu KR-8793"
        wpis = "Jan Lis, nr wpisu: WA-123"
        wynik = {"mocodawca": [{"data": {"imie_nazwisko": mocodawca, "nazwa": mocodawca},
                                "podpisujacy": [{"imie_nazwisko": podpis}]}],
                 "pelnomocnicy": [{"imie_nazwisko": pelnomocnik}, {"imie_nazwisko": wpis}]}
        self.regula("\n".join((mocodawca, podpis, pelnomocnik, wpis)), wynik)
        self.assertEqual(wynik["mocodawca"][0]["data"], {"imie_nazwisko": "Anna Nowak-Kowalska", "nazwa": mocodawca})
        self.assertEqual(wynik["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Halina Baran"}])
        self.assertEqual(wynik["pelnomocnicy"], [{"imie_nazwisko": "Mateusz Wierzbicki"}, {"imie_nazwisko": "Jan Lis"}])

    def test_pozostawia_niejasny_dopisek_i_nazwisko_niepotwierdzone_w_tekscie(self):
        wpisy = [
            "Anna Nowak-Kowalska", "Anna Nowak - Kowalska", "Jan Lis — adwokat i Anna Bąk",
            "Jan Lis, kancelaria adwokacka", "Jan Lis — nr wpisu nieustalony", "Jan Lis – Członek Zarządu spółki Alfa",
        ]
        osoby = [{"imie_nazwisko": wartosc} for wartosc in (*wpisy, "Ewa Bąk — Prokurent")]
        wynik = {"pelnomocnicy": deepcopy(osoby)}
        self.regula("\n".join(wpisy), wynik)
        self.assertEqual(wynik["pelnomocnicy"], osoby)

    def test_funkcja_w_jednoznacznej_stopce_nie_jest_druga_osoba(self):
        naglowek = TEKST.split("Podpisy:")[0]
        stopka = "Data\n12 maja 2025\n............\nJan Nowak\nProkurent\n(podpis i pieczęć)"
        osoba = {"imie_nazwisko": "Jan Nowak"}
        funkcja = {"imie_nazwisko": "Prokurent"}
        inna = {"imie_nazwisko": "Anna Lis"}
        for tekst, osoby, oczekiwane in (
            (naglowek + stopka, [osoba, funkcja], [osoba]),
            (naglowek + stopka, [osoba, inna], [osoba, inna]),
            (stopka, [osoba, funkcja], [osoba, funkcja]),
            (naglowek + "Podpisy:\nAnna Lis\nDyrektor\n" + stopka, [osoba, funkcja], [osoba, funkcja]),
        ):
            with self.subTest(tekst=tekst, osoby=osoby):
                self.wynik["mocodawca"][0]["podpisujacy"] = deepcopy(osoby)
                self.regula(tekst, self.wynik)
                self.assertEqual(self.wynik["mocodawca"][0]["podpisujacy"], oczekiwane)

    def test_podpis_po_nazwanej_deklaracji_i_przed_przyjeciem(self):
        deklaracja = (
            "PEŁNOMOCNICTWO\nFirma Alfa S.A., ul. Klonowa 3, 10-220 Olsztyn, "
            "KRS 0000000001, NIP 0123456789, REGON 123456785 (dalej: „Mocodawca”), "
            "reprezentowana przez osoby podpisane poniżej, udziela pełnomocnictwa: adw. Ewa Lis.\n"
        )
        stopka = "Mocodawca:\n..........\nJan Nowak\nPrezes Zarządu\nPełnomocnictwo przyjmuję:\n..........\nadw. Ewa Lis"
        osoba = {"imie_nazwisko": "Jan Nowak"}
        for tekst, krs, ile in (
            (deklaracja + stopka, "0000000001", 1),
            (deklaracja.replace("Firma Alfa", "Firma Gamma") + stopka, "0000000001", 2),
            (deklaracja + stopka, None, 2),
            (deklaracja + stopka, "0000000002", 2),
        ):
            with self.subTest(tekst=tekst, krs=krs):
                self.dane.update(krs=krs, nip="0123456789")
                self.wynik["mocodawca"][0]["podpisujacy"] = [osoba, osoba]
                self.regula(tekst, self.wynik)
                self.assertEqual(self.wynik["mocodawca"][0]["podpisujacy"], [osoba] * ile)

    def test_nie_zastepuje_listy_szablonem_lub_fragmentem_bloku_podpisow(self):
        blok = "W imieniu Firma Alfa S.A.:\n........\nEwa Lis\nPrezes Zarządu"
        for tekst in (
            blok.replace("Ewa Lis", "Imię Nazwisko"),
            "Podpisy:\nAnna Nowak\nWiceprezes Zarządu\n" + blok,
            "Podpisy mocodawcy:\nAnna Nowak, Wiceprezes Zarządu\n" + blok,
            "Załącznik – wzór podpisu (wypełniony przykładowo):\n" + blok,
            blok + "\nPełnomocnictwo przyjmuję:\n........\nadw. Jan Nowak\n"
                   "Podpis drugiego członka zarządu mocodawcy:\n........\nAnna Nowak\nWiceprezes Zarządu",
        ):
            with self.subTest(tekst=tekst):
                rekord = {"data": {"nazwa": "Firma Alfa S.A."}, "podpisujacy": [
                    {"imie_nazwisko": "Anna Nowak"}, {"imie_nazwisko": "Ewa Lis"},
                ]}
                wynik = {"mocodawca": [deepcopy(rekord)]}
                self.regula(tekst, wynik)
                self.assertEqual(wynik["mocodawca"], [rekord])

    def test_uzupelnia_dane_z_sekcji_mocodawcy(self):
        self.regula(TEKST, self.wynik)
        self.assertEqual(self.dane, {
            "nazwa": "Firma Alfa S.A.", "krs": "0000000001", "nip": "0123456789", "typ": "osoba_prawna",
        })

    def test_rozdziela_sklejonych_umocowanych_z_pesel_przy_jednej_osobie(self):
        tekst = ("Udzielam pełnomocnictwa adw. Anna Lis, PESEL: 01234567890 (nr wpisu: KR-123), "
                 "r. pr. Jan Nowak (nr wpisu: WA-124), do reprezentowania spółki.\n"
                 "Mocodawca:\n........\nEwa Bąk")
        wynik = {"pelnomocnicy": [{"imie_nazwisko": "Anna Lis Jan Nowak", "pesel": None}]}
        self.regula(tekst, wynik)
        self.regula(tekst, wynik)
        self.assertEqual(wynik["pelnomocnicy"], [{"imie_nazwisko": "Anna Lis", "pesel": "01234567890"},
                                                {"imie_nazwisko": "Jan Nowak", "pesel": None}])

    def test_pelna_rubryka_pomija_podpisujacego_i_dodaje_druga_osobe(self):
        tekst = ("Mocodawca:\nAnna Lis\nPEŁNOMOCNICY:\nr. pr. Adam Nowak\nnr wpisu: WA-123\n"
                 "adw. Maria Kot\nnr wpisu: KR-124\nZakres umocowania:\ndo reprezentowania spółki.\nPodpisy:\nEwa Bąk")
        osoba = {"imie_nazwisko": "Adam Nowak", "pesel": None}
        for dokument, oczekiwani in (
            (tekst, [osoba, {"imie_nazwisko": "Maria Kot", "pesel": None}]),
            (tekst.replace("adw. Maria Kot", "asystent Maria Kot"), [osoba]),
            (tekst.replace("Zakres umocowania:", "Inna treść:"), [osoba]),
        ):
            with self.subTest(dokument=dokument):
                wynik = {"pelnomocnicy": [osoba.copy()]}
                self.regula(dokument, wynik)
                self.assertEqual(wynik["pelnomocnicy"], oczekiwani)

    def test_nie_zastepuje_mianownika_odmienionym_nazwiskiem_ani_podpisem_mocodawcy(self):
        osoba = {"imie_nazwisko": "Jan Nowak", "pesel": None}
        dokument = "Udzielam pełnomocnictwa adw. Janowi Nowakowi (nr wpisu: WA-123) do reprezentowania spółki."
        podpis = "\nMocodawca:\n........\nadw. Janowi Nowakowi"
        for tekst in (dokument, dokument + podpis, dokument.replace("Udzielam", "Nie udzielam")):
            wynik = {"pelnomocnicy": [osoba.copy()]}
            self.regula(tekst, wynik)
            self.assertEqual(wynik["pelnomocnicy"], [osoba])

    def test_sprzeczne_nadania_lub_dodatkowy_pesel_wstrzymuja_zmiane(self):
        tekst = "Ustanawiam pełnomocnikiem adw. Anna Lis (nr wpisu: KR-281) do reprezentowania spółki."
        for dokument, pesel in ((tekst + " Udzielam pełnomocnictwa również innej osobie.", None),
                                (tekst, "01234567890")):
            stary = [{"imie_nazwisko": "adw. Anna Lis", "pesel": pesel}]
            wynik = {"pelnomocnicy": deepcopy(stary)}
            self.regula(dokument, wynik)
            self.assertEqual(wynik["pelnomocnicy"], stary)

    def test_pomija_wielu_mocodawcow(self):
        self.wynik["mocodawca"].append({"data": {"nazwa": "Firma Beta S.A.", "nip": None}})
        przed = deepcopy(self.wynik)
        self.regula(TEKST, self.wynik)
        self.assertEqual(self.wynik, przed)

    def test_pomija_nazwe_bedaca_fragmentem_nazwy_mocodawcy(self):
        self.dane["nazwa"] = "Alfa S.A."
        przed = deepcopy(self.wynik)
        self.regula(TEKST, self.wynik)
        self.assertEqual(self.wynik, przed)

    def test_powtorzona_etykieta_nip_zachowuje_wartosc_modelu(self):
        self.dane["nip"] = "1111111111"
        tekst = TEKST.replace("NIP 0123456789", "NIP 0123456789, NIP 9876543210")
        self.regula(tekst, self.wynik)
        self.assertEqual(self.dane["nip"], "1111111111")
        self.assertEqual(self.dane["krs"], "0000000001")

    def test_podpisy_przypisuje_do_nazwanej_firmy_i_pomija_przyjecie(self):
        tekst = """W imieniu Firma Alfa S.A.:
..................
Maria Nowak-Kowalska
Prezes Zarządu
W imieniu Firma Beta sp.j.:
..................
Irena Lis
Wspólnik
..................
Adam Bąk
Prokurent
Pełnomocnictwo przyjmuję:
..................
adw. Jan Nowak
"""
        wynik = {"mocodawca": [
            {"data": {"nazwa": "Firma Beta sp.j."}, "podpisujacy": []},
            {"data": {"nazwa": "Firma Alfa S.A."}, "podpisujacy": []},
        ]}
        self.regula(tekst, wynik)
        self.assertEqual(wynik["mocodawca"][0]["podpisujacy"], [
            {"imie_nazwisko": "Irena Lis"}, {"imie_nazwisko": "Adam Bąk"},
        ])
        self.assertEqual(wynik["mocodawca"][1]["podpisujacy"], [{"imie_nazwisko": "Maria Nowak-Kowalska"}])

    def test_nie_publikuje_czesciowego_bloku_podpisow(self):
        rekord = {"data": {"nazwa": "Firma Alfa S.A."}, "podpisujacy": [{"imie_nazwisko": "Jan Nowak"}]}
        pierwszy = "W imieniu Firma Alfa S.A.:\n........\nAnna Lis\nProkurent\n"
        for koniec in (
            "W imieniu Inna Firma:\n........\nEwa Bąk\nDyrektor",
            "........\nAnna Lis i Ewa Nowak\nDyrektor",
            "........\nAnna Lis",
            "Pełnomocnictwo przyjmuję:\nW imieniu Firma Alfa S.A.:\n........\nEwa Bąk\nProkurent",
        ):
            with self.subTest(koniec=koniec):
                wynik = {"mocodawca": [deepcopy(rekord)]}
                self.regula(pierwszy + koniec, wynik)
                self.assertEqual(wynik["mocodawca"], [rekord])

    def test_za_firme_dotyczy_tylko_jednego_podpisu(self):
        dane = {"mocodawca": [{"data": {"nazwa": "Firma Alfa S.A."}, "podpisujacy": []}]}
        podpis = "........\nZa Firma Alfa S.A.\nAnna Lis\nProkurent"
        wynik = deepcopy(dane)
        self.regula(podpis, wynik)
        self.assertEqual(wynik["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Anna Lis"}])
        wynik = deepcopy(dane)
        self.regula(podpis + "\n........\nMaria Bąk\nDyrektor", wynik)
        self.assertEqual(wynik, dane)

    def test_rubryka_mocodawca_wymaga_potwierdzenia_podmiotu_w_tekscie(self):
        self.wynik["mocodawca"][0]["podpisujacy"] = []
        podpis = "Mocodawca:\n........\nAnna Lis\nProkurent"
        self.regula(podpis, self.wynik)
        self.assertEqual(self.wynik["mocodawca"][0]["podpisujacy"], [])
        sekcja = TEKST.split("Podpisy:")[0].replace("KRS 0000000001", "KRS (nieczytelny)")
        self.regula(sekcja + podpis, self.wynik)
        self.assertEqual(self.wynik["mocodawca"][0]["podpisujacy"], [])
        self.regula(TEKST.split("Podpisy:")[0] + podpis, self.wynik)
        self.assertEqual(self.wynik["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Anna Lis"}])

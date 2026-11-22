import unittest
from pathlib import Path
from unittest.mock import Mock

from odwolania.pipeline import DocumentPipeline
from odwolania.rules import empty_result
from odwolania.templates import TemplateRegistry


WZORCE = Path(__file__).resolve().parents[1] / "oczekiwane-json"
ODWOLANIE = """ODWOŁANIE
Działając w imieniu wykonawcy, wnoszę odwołanie wobec czynności Zamawiającego, polegających na:
1) odrzuceniu oferty z dnia 26 lutego 2026 r.;
2) wykluczeniu wykonawcy.
Zarzut nr 1 – odrzucenia oferty:
Informacja o zaskarżonej czynności została przekazana w dniu 26 lutego 2026 r.
"""


class DatyOdwolaniaTest(unittest.TestCase):
    def setUp(self):
        self.rejestr = TemplateRegistry.load(WZORCE)
        self.wzorzec = self.rejestr.classify(ODWOLANIE)

    def test_pipeline_przywraca_lokalna_date_i_kod_tego_samego_zarzutu(self):
        model = Mock()
        model.extract_text.return_value = empty_result(self.wzorzec.shape)
        pipeline = DocumentPipeline(None, self.rejestr, model)
        wynik = pipeline._extract(ODWOLANIE, ODWOLANIE, {}, self.wzorzec)["OdwolanieKIO"]
        self.assertEqual(wynik["czynnosc_dzien"], "2026-02-26")
        self.assertEqual(wynik["czynnosc_powod_id"], 1)
        self.assertIsNone(wynik["data"])

    def test_datuje_czynnosc_z_deklaracji_tuz_przed_pierwszym_zarzutem(self):
        wzor = (
            "ODWOŁANIE\nGdynia, dnia 5 stycznia 2027 roku\n"
            "Działając na podstawie ustawy z dnia 11 września 2019 roku, wnoszę o:\n"
            "Zamawiający w dniu 28 grudnia 2026 roku\nnie odrzucił oferty.\n"
            "Zarzut nr 1 naruszenia zasady równego traktowania wykonawców:\n"
            "Zamawiający zróżnicował kryteria.\n"
            "Zarzut nr 2 naruszenia przepisów o publikacji:\n"
            "Zamawiający opublikował dokumentację w dniu 10 grudnia 2026 roku."
        )
        model = Mock()
        model.extract_text.return_value = empty_result(self.wzorzec.shape)
        wynik = DocumentPipeline(None, self.rejestr, model)._extract(wzor, wzor, {}, self.wzorzec)
        self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_dzien"], "2026-12-28")
        self.assertEqual(wynik["OdwolanieKIO"]["czynnosc_powod_id"], 7)
        self.assertEqual(wynik["OdwolanieKIO"]["data"], "2027-01-05")

        for tekst in (
            wzor.replace("28 grudnia", "32 grudnia"),
            wzor.replace("28 grudnia", "27 lub 28 grudnia"),
            wzor.replace("nie odrzucił oferty.", "nie odrzucił oferty. Następnie unieważnił postępowanie."),
            wzor.replace("Działając", "Załącznik nr 2 — przykład wcześniejszego odwołania\nDziałając"),
            wzor.replace("wnoszę o:", "nie wnoszę o:"),
            wzor.replace("wnoszę o:", "nie\nwnoszę o:"),
            wzor.replace("Działając", "Dosłownie cytuję z poprzedniej sprawy.\nDziałając"),
            wzor.replace("Zamawiający zróżnicował", "Zaskarżoną czynność podjęto w dniu 30 grudnia 2026 roku. Zamawiający zróżnicował"),
            wzor + "\nZawiadomienie o zaskarżonej czynności doręczono dnia 29 grudnia 2026 roku.",
            wzor + "\nInformację o zaskarżonej czynności doręczono dopiero następnego dnia.",
            wzor + "\nZawiadomienie o zaskarżonej czynności doręczono Odwołującemu 29.12.2026 r.",
            wzor.replace("naruszenia zasady równego traktowania wykonawców", "unieważnienia postępowania"),
        ):
            with self.subTest(tekst=tekst):
                dane = {"czynnosc_dzien": None}
                self.wzorzec.apply_rules(tekst, {"OdwolanieKIO": dane})
                self.assertIsNone(dane["czynnosc_dzien"])

        bez_przecinka = wzor.replace("Działając na podstawie ustawy z dnia 11 września 2019 roku,",
                                     "Działając w imieniu wykonawcy")
        dane = {"czynnosc_dzien": None}
        self.wzorzec.apply_rules(bez_przecinka, {"OdwolanieKIO": dane})
        self.assertEqual(dane["czynnosc_dzien"], "2026-12-28")

    def test_brak_dwoch_zgodnych_zrodel_lub_juz_ustalona_data(self):
        obce_zdarzenie = "Zamawiający w dniu 26 lutego 2026 roku odrzucił ofertę.\nZarzut nr 1: publikacja SWZ."
        for tekst, poprzednia in (
            (ODWOLANIE.replace("została przekazana w dniu 26", "została przekazana w dniu 24"), None),
            (ODWOLANIE.replace("z dnia 26 lutego 2026 r.", "z dnia 30 lutego 2026 r."), None),
            (ODWOLANIE.replace("z dnia 26 lutego 2026 r.", "z dnia 25 lub 26 lutego 2026 r."), None),
            (ODWOLANIE, "2026-02-24"),
            (obce_zdarzenie, None),
        ):
            dane = {"czynnosc_dzien": poprzednia}
            with self.subTest(tekst=tekst, poprzednia=poprzednia):
                self.wzorzec.apply_rules(tekst, {"OdwolanieKIO": dane})
                self.assertEqual(dane["czynnosc_dzien"], poprzednia)

    def test_usuwa_wylacznie_date_w_jawnie_innej_roli(self):
        czyn = "Działając w imieniu wykonawcy, składam odwołanie.\nZamawiający w dniu 2 marca 2026 roku odrzucił ofertę."
        for tekst, oczekiwana in (
            ("ODWOŁANIE\n" + czyn, None),
            ("ODWOŁANIE\n" + czyn + "\n02.03.2026 — wniesienie odwołania.", "2026-03-02"),
            ("ODWOŁANIE\n" + czyn + "\nTego samego dnia wniesiono odwołanie.", "2026-03-02"),
            ("ODWOŁANIE\n" + "Dane kontaktowe\n" * 51 + "Data pisma: 02.03.2026\n" + czyn, "2026-03-02"),
            ("ODWOŁANIE\nDziałając w imieniu wykonawcy, składam odwołanie.", "2026-03-02"),
        ):
            dane = {"data": "2026-03-02"}
            with self.subTest(tekst=tekst):
                self.wzorzec.apply_rules(tekst, {"OdwolanieKIO": dane})
                self.assertEqual(dane["data"], oczekiwana)

    def test_pipeline_sprawdza_date_modelu_przed_formatowaniem(self):
        tekst = "ODWOŁANIE\nDziałając w imieniu wykonawcy, wnoszę odwołanie.\nZamawiający w dniu 3 kwietnia 2026 roku odrzucił ofertę."
        odpowiedz = empty_result(self.wzorzec.shape)
        odpowiedz["OdwolanieKIO"]["data"] = " 03.04.2026 "
        model = Mock()
        model.extract_text.return_value = odpowiedz
        wynik = DocumentPipeline(None, self.rejestr, model)._extract(tekst, tekst, {}, self.wzorzec)
        self.assertIsNone(wynik["OdwolanieKIO"]["data"])

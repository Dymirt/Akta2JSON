import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from odwolania.cli import BatchProcessor
from odwolania.extraction import DocumentExtractor
from odwolania.mistral import MistralClient
from odwolania.pipeline import DocumentPipeline
from odwolania.templates import DocumentTemplate, TemplateRegistry


def klient_z_odpowiedzia(odpowiedz):
    klient = Mock(spec=MistralClient)
    klient.complete.return_value = odpowiedz
    return klient


class TestOdzyskJSON(TestCase):
    def test_odzyskuje_polskie_klucze_pelnomocnikow_z_jednej_odpowiedzi(self):
        plik = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "pelnomocnictwo.jsonc"
        wzorzec = DocumentTemplate.load(plik)
        kandydat = {"mocodawca": [], "pełnomocnicy": [
            {"imię_nazwisko": "[OSOBA_1]", "pesel": "[PESEL_1]"},
            {"imie_nazwisko": "[OSOBA_2]", "pesel": None},
        ]}
        tekst = "Udziela pełnomocnictwa [OSOBA_1], PESEL: [PESEL_1], oraz [OSOBA_2]."
        mapa = {"[OSOBA_1]": "A", "[PESEL_1]": "00000000000", "[OSOBA_2]": "B"}
        klient = klient_z_odpowiedzia(json.dumps(kandydat))
        wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, mapa)
        self.assertEqual(wynik, {"mocodawca": [], "pelnomocnicy": [
            {"imie_nazwisko": "[OSOBA_1]", "pesel": "[PESEL_1]"},
            {"imie_nazwisko": "[OSOBA_2]", "pesel": None},
        ]})
        klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_wariant_pisowni_zachowuje_typy_i_weryfikacje_znacznikow(self):
        wzorzec = DocumentTemplate.parse("raport", '{"osoby":[{"imię":"[OSOBA]", "numer":0}]}')
        kandydat = {"osoby": [
            {"imie": "[OSOBA_8]", "numer": 1},
            {"imie": "[OSOBA_2]", "numer": "2"},
        ]}
        tekst = "[OSOBA_2]"
        klient = klient_z_odpowiedzia(json.dumps(kandydat))
        wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, {"[OSOBA_2]": "A"})
        self.assertEqual(wynik, {"osoby": [
            {"imię": None, "numer": 1},
            {"imię": "[OSOBA_2]", "numer": None},
        ]})
        klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_pojedynczy_pelnomocnik_jest_odzyskiwany_tylko_z_jawnego_aliasu(self):
        plik = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "pelnomocnictwo.jsonc"
        wzorzec = DocumentTemplate.load(plik)
        self.assertNotIn("@singleton", wzorzec.prompt)
        tekst = "Udziela pełnomocnictwa [OSOBA_1]."
        rekord = {"imie_nazwisko": "[OSOBA_1]", "nr": "12"}
        for odpowiedz, oczekiwani in (
            ({"pełnomocnik": rekord}, [{"imie_nazwisko": "[OSOBA_1]", "pesel": None}]),
            ({"pełnomocnik": {"imie_nazwisko": "[OSOBA_9]"}}, []),
            ({"podpisujacy": rekord}, []),
            ({"pełnomocnik": [rekord]}, []),
            ({"pelnomocnicy": [], "pełnomocnik": rekord}, []),
            ({"pełnomocnicy": None, "pełnomocnik": rekord}, []),
        ):
            with self.subTest(odpowiedz=odpowiedz):
                klient = klient_z_odpowiedzia(json.dumps({"mocodawca": [], **odpowiedz}))
                wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, {"[OSOBA_1]": "A"})
                self.assertEqual(wynik, {"mocodawca": [], "pelnomocnicy": oczekiwani})
                klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_konfiguracja_pojedynczego_rekordu_jest_lokalna_dla_obiektu(self):
        struktura = '{"lista":[{"osoby":[{"opis":""}]}],"osoby":[{"opis":""}]}'
        wzorzec = DocumentTemplate.parse("raport", "// @singleton lista.*.osoby osoba\n" + struktura)
        rekord = {"opis": "A"}
        klient = klient_z_odpowiedzia(json.dumps({"lista": [{"osoba": rekord}], "osoba": rekord}))
        self.assertEqual(DocumentExtractor(klient).extract_text("", wzorzec, {}), {
            "lista": [{"osoby": [rekord]}], "osoby": [],
        })
        klient.complete.assert_called_once()

    def test_odrzuca_bledne_lub_kolidujace_dyrektywy_singleton_przy_wczytaniu(self):
        struktura = '{"osoby":[{"opis":""}],"mocodawcy":[{"opis":""}],"koszty":[0],"imię":""}'
        for dyrektywy in (
            ["osoby"], ["brak osoba"], ["koszty koszt"], ["imię osoba"], ["osoby imie"],
            ["osoby osoba", "osoby adresat"], ["osoby pełnomocnik", "mocodawcy pelnomocnik"],
        ):
            with self.subTest(dyrektywy=dyrektywy), self.assertRaisesRegex(ValueError, "@singleton"):
                linie = ["// @singleton " + d for d in dyrektywy]
                DocumentTemplate.parse("raport", "\n".join([*linie, struktura]))

    def test_pierwszenstwo_dokladnego_klucza_i_pominiecie_niejednoznacznych_aliasow(self):
        for struktura, kandydat, oczekiwany in (
            ({"zrodlo": ""}, {"zrodlo": None, "źródło": "A"}, {"zrodlo": None}),
            ({"zrodlo": [""]}, {"zrodlo": [], "źródło": ["A"]}, {"zrodlo": []}),
            ({"zrodlo": ""}, {"źródło": "A", "żrodlo": "B"}, {"zrodlo": None}),
            ({"zrodlo": "", "źródło": ""}, {"zrodlo": "A", "żrodlo": "B"}, {"zrodlo": "A", "źródło": None}),
        ):
            with self.subTest(struktura=struktura, kandydat=kandydat):
                wzorzec = DocumentTemplate.parse("raport", json.dumps(struktura))
                klient = klient_z_odpowiedzia(json.dumps(kandydat))
                wynik = DocumentExtractor(klient).extract_text("", wzorzec, {})
                self.assertEqual(wynik, oczekiwany)
                klient.complete.assert_called_once_with(wzorzec.prompt, "")

    def test_lokalnie_usuwa_jedno_ogrodzenie_json_i_waliduje_wartosci(self):
        wzorzec = DocumentTemplate.parse("raport", '{"numer":"[KRS]", "uwaga":""}')
        tekst = "KRS: [KRS_1]"
        mapa = {"[KRS_1]": "0000000001"}
        for numer, oczekiwany in (("[KRS_1]", "[KRS_1]"), ("[KRS_9]", None)):
            with self.subTest(numer=numer):
                odpowiedz = json.dumps({"numer": numer, "uwaga": "Opis"})
                klient = klient_z_odpowiedzia(f"```json\n{odpowiedz}\n```")
                wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, mapa)
                self.assertEqual(wynik, {"numer": oczekiwany, "uwaga": "Opis"})
                klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_rozpoznaje_tylko_jednoznaczna_dodatkowa_otoczke_typu(self):
        wzorzec = DocumentTemplate.parse("raport", '{"dane":{"kwota":0.0}}')
        pola = {"dane": {"kwota": 10}}
        pusty = {"dane": {"kwota": None}}
        for kandydat, oczekiwany in (
            ({"raport": pola}, pola),
            ({"inny_typ": pola}, pusty),
            ({"raport": pola, "druga": pola}, pusty),
        ):
            with self.subTest(kandydat=kandydat):
                klient = klient_z_odpowiedzia(json.dumps(kandydat))
                wynik = DocumentExtractor(klient).extract_text("Kwota: 10", wzorzec, {})
                self.assertEqual(wynik, oczekiwany)
                klient.complete.assert_called_once_with(wzorzec.prompt, "Kwota: 10")

    def test_odzyskuje_pelnomocnikow_pod_otoczka_typu(self):
        plik = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "pelnomocnictwo.jsonc"
        wzorzec = DocumentTemplate.load(plik)
        tekst = "[OSOBA_1]"
        mapa = {"[OSOBA_1]": "A"}
        rekord = {"imie_nazwisko": "[OSOBA_1]", "pesel": None}
        for pola, oczekiwani in (
            ({"pełnomocnicy": [rekord]}, [rekord]),
            ({"pełnomocnik": rekord}, [rekord]),
            ({"obcy_klucz": [rekord]}, []),
        ):
            with self.subTest(klucze=list(pola)):
                klient = klient_z_odpowiedzia(json.dumps({"pelnomocnictwo": pola}))
                wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, mapa)
                self.assertEqual(wynik, {"mocodawca": [], "pelnomocnicy": oczekiwani})
                klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_zachowuje_klucz_typu_bedacy_czescia_wzorca(self):
        wzorzec = DocumentTemplate.parse("raport", '{"raport":{"kwota":0}}')
        wynik = {"raport": {"kwota": 12}}
        klient = klient_z_odpowiedzia(json.dumps(wynik))
        self.assertEqual(DocumentExtractor(klient).extract_text("", wzorzec, {}), wynik)

    def test_zachowuje_prawidlowe_elementy_uszkodzonej_listy_w_kolejnosci(self):
        wzorzec = DocumentTemplate.parse("raport", '{"osoby":[{"osoba":"[OSOBA]", "rola":""}]}')
        kandydat = {"osoby": [
            {"osoba": "[OSOBA_1]", "rola": 25},
            {"osoba": "[OSOBA_2]", "rola": "dyrektor"},
        ]}
        tekst = "[OSOBA_1] oraz [OSOBA_2] – dyrektor"
        klient = klient_z_odpowiedzia(json.dumps(kandydat))
        wynik = DocumentExtractor(klient).extract_text(tekst, wzorzec, {"[OSOBA_1]": "A", "[OSOBA_2]": "B"})
        self.assertEqual(wynik, {"osoby": [
            {"osoba": "[OSOBA_1]", "rola": None},
            {"osoba": "[OSOBA_2]", "rola": "dyrektor"},
        ]})
        klient.complete.assert_called_once_with(wzorzec.prompt, tekst)

    def test_blad_transportu_jest_przekazywany_wywolujacemu(self):
        wzorzec = DocumentTemplate.parse("raport", '{"kwota":0.0}')
        klient = Mock(spec=MistralClient)
        awaria = RuntimeError("Nie udało się odebrać odpowiedzi z Mistral EU.")
        klient.complete.side_effect = awaria
        with self.assertRaises(RuntimeError) as blad:
            DocumentExtractor(klient).extract_text("Raport", wzorzec, {})
        self.assertIs(blad.exception, awaria)
        klient.complete.assert_called_once_with(wzorzec.prompt, "Raport")

    def test_nieskonczona_kwota_nie_usuwa_poprawnego_opisu(self):
        wzorzec = DocumentTemplate.parse("raport", '{"kwota":0.0, "opis":""}')
        klient = klient_z_odpowiedzia('{"kwota":1e999, "opis":"Opłata za wpis"}')

        wynik = DocumentExtractor(klient).extract_text("Opis: Opłata za wpis", wzorzec, {})

        self.assertEqual(wynik, {"kwota": None, "opis": "Opłata za wpis"})
        klient.complete.assert_called_once()

    def test_nieczytelna_odpowiedz_zachowuje_w_wyniku_wszystkie_pola_lokalne(self):
        nadawca = "00111111111111111111111111"
        odbiorca = "00222222222222222222222222"
        tekst = (
            "POTWIERDZENIE PRZELEWU\nData operacji: 31.03.2026\nKwota: 123,45 PLN\n"
            f"Z rachunku: {nadawca}\nNa rachunek: {odbiorca}\nNumer transakcji: REF-01"
        )
        mapa = {"[RACHUNEK_1]": nadawca, "[RACHUNEK_2]": odbiorca, "[NR_TRANSAKCJI_1]": "REF-01"}
        zanonimizowany = tekst
        for znacznik, wartosc in mapa.items():
            zanonimizowany = zanonimizowany.replace(wartosc, znacznik)
        procesor = BatchProcessor(Mock(return_value=tekst), Mock(return_value=(zanonimizowany, mapa)))
        wzorzec = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "przelew.jsonc"
        klient = klient_z_odpowiedzia('{"przelew_bankowy":')
        pipeline = DocumentPipeline(
            procesor, TemplateRegistry((DocumentTemplate.load(wzorzec),)), DocumentExtractor(klient),
        )

        with TemporaryDirectory() as katalog:
            baza = Path(katalog)
            self.assertEqual(pipeline.run([(baza / "plik.pdf", baza / "plik.txt")]), 0)
            wynik = json.loads((baza / "plik.json").read_text(encoding="utf-8"))

        self.assertEqual(wynik, {"przelew_bankowy": {
            "data_operacji": "2026-03-31", "kwota": 123.45, "na_rachunek": odbiorca,
            "numer_transakcji": "REF-01", "tytul": None, "z_rachunku": nadawca,
        }})
        klient.complete.assert_called_once()
        for wartosc in mapa.values():
            self.assertNotIn(wartosc, str(klient.mock_calls))

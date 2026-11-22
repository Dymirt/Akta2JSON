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

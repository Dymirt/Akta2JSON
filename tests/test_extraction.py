import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import httpx

from odwolania.extraction import DocumentExtractor, restore_markers
from odwolania.mistral import MistralClient
from odwolania.templates import DocumentTemplate


class ExtractionTest(unittest.TestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        root = Path(workspace.name)
        self.text = root / "odwolanie.txt"
        self.template = root / "odwolanie.jsonc"
        self.document = "Odwołujący: [PODMIOT_1]\nKRS: [KRS_1]\nTytuł: [TYTUL_1]\n[TYTUL_2]"
        self.config = """{
          // Dopasuj do odwołującego.
          "strony": [{"nazwa":"[PODMIOT]", "krs":"[KRS]"}],
          "tytul":"[TYTUL]",
          "url":"https://example.org"
        }"""
        self.text.write_text(self.document, encoding="utf-8")
        self.template.write_text(self.config, encoding="utf-8")
        self.text.with_suffix(".mapa.json").write_text(json.dumps({
            "[PODMIOT_1]": "Poufna nazwa",
            "[KRS_1]": "0000012345",
            "[TYTUL_1]": "Część pierwsza",
            "[TYTUL_2]": "Część druga",
        }), encoding="utf-8")
        self.result = {
            "strony": [{"nazwa": "[PODMIOT_1]", "krs": "[KRS_1]"}],
            "tytul": "[TYTUL_1] [TYTUL_2]",
            "url": None,
        }

    def test_sends_the_whole_document_and_template_without_map_values(self):
        client = MistralClient("test-key", "test-model")
        source = self.document + "\n\nPodpisy\fStrona druga\n"
        self.text.write_text(source, encoding="utf-8")
        for answer, expected in (
            (self.result, self.result),
            ({"tytul": "[TYTUL_2]"}, {"strony": [], "tytul": "[TYTUL_2]", "url": None}),
        ):
            with self.subTest(answer=answer):
                response = httpx.Response(200, json={
                    "id": "cmpl-test", "object": "chat.completion", "created": 1, "model": "test-model",
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": json.dumps(answer)}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                })
                with patch("httpx.HTTPTransport.handle_request", return_value=response) as send:
                    self.assertEqual(DocumentExtractor(client).extract(self.text, self.template), expected)
                send.assert_called_once()
                request = send.call_args.args[0]
                payload = json.loads(request.content)
                self.assertEqual(str(request.url), "https://api.eu.mistral.ai/v1/chat/completions")
                system, user = payload["messages"]
                self.assertEqual(system["role"], "system")
                self.assertIn("json", system["content"].lower())
                self.assertIn(self.config, system["content"])
                self.assertEqual(user, {"role": "user", "content": source})
                self.assertEqual(payload["model"], "test-model")
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                self.assertNotIn("Poufna nazwa", str(payload))
                self.assertNotIn("0000012345", str(payload))

    def test_recovers_valid_fields_from_invalid_structure_or_marker(self):
        candidates = (
            ({**self.result, "inne": None}, self.result),
            ({**self.result, "tytul": "[TYTUL_999]"}, {**self.result, "tytul": None}),
            (
                {**self.result, "strony": [{"nazwa": "Wymyślona firma", "krs": "[KRS_1]"}]},
                {**self.result, "strony": [{"nazwa": None, "krs": "[KRS_1]"}]},
            ),
            ({**self.result, "tytul": "[KRS_1]"}, {**self.result, "tytul": None}),
        )
        for candidate, expected in candidates:
            with self.subTest(candidate=candidate):
                client = Mock(spec=MistralClient)
                client.complete.return_value = json.dumps(candidate)
                self.assertEqual(DocumentExtractor(client).extract(self.text, self.template), expected)
                client.complete.assert_called_once()

    def test_ambiguous_or_unparseable_text_leaves_an_empty_typed_result(self):
        valid = json.dumps(self.result)
        for response in (f"Wynik:\n{valid}", f"```json\n{valid}\n```\n```json\n{valid}\n```", f"{valid}\n{valid}"):
            with self.subTest(response=response):
                client = Mock(spec=MistralClient)
                client.complete.return_value = response
                self.assertEqual(DocumentExtractor(client).extract(self.text, self.template),
                                 {"strony": [], "tytul": None, "url": None})
                client.complete.assert_called_once()

    def test_extracted_fragment_keeps_text_and_restores_all_its_markers(self):
        template = DocumentTemplate.parse("przelew", """{
            // Przepisz pełną treść pola „Tytuł” znak w znak, bez etykiety.
            "tytul": "",
            "numer_transakcji": null
        }""")
        fragment = 'Załącznik "A" —  [PODMIOT_1].\nNumer: [NR_TRANSAKCJI_1].'
        document = f"Tytuł:\n{fragment}\nNumer referencyjny: [NR_TRANSAKCJI_1]"
        mapping = {"[PODMIOT_1]": "Firma z PDF", "[NR_TRANSAKCJI_1]": "TR123"}
        client = Mock(spec=MistralClient)
        markers = {"tytul": fragment, "numer_transakcji": "[NR_TRANSAKCJI_1]"}
        client.complete.return_value = json.dumps(markers)

        extracted = DocumentExtractor(client).extract_text(document, template, mapping)

        self.assertEqual(extracted, markers)
        self.assertEqual(restore_markers(extracted, mapping, template.formatters), {
            "tytul": 'Załącznik "A" — Firma z PDF. Numer: TR123.',
            "numer_transakcji": "TR123",
        })
        client.complete.assert_called_once_with(template.prompt, document)

    def test_normalizes_spaces_in_nested_text_values_after_restoring_markers(self):
        mapping = {"[OSOBA_1]": "Łukasz\r\n   Żółć"}
        fields = {
            "osoby": [{"nazwa": "[OSOBA_1]   (pełnomocnik)"}],
            "uwagi": ["  Pierwsza\n\nstrona\fdruga.  ", " \t "],
            "kwota": 12.5, "liczba": 3, "potwierdzone": True, "brak": None,
        }
        self.assertEqual(restore_markers(fields, mapping), {
            "osoby": [{"nazwa": "Łukasz Żółć (pełnomocnik)"}],
            "uwagi": ["Pierwsza strona druga.", ""],
            "kwota": 12.5, "liczba": 3, "potwierdzone": True, "brak": None,
        })

    def test_appeal_party_nips_keep_leading_zeros_after_restoring_markers(self):
        path = Path(__file__).resolve().parents[1] / "oczekiwane-json/odwolanie.jsonc"
        template = DocumentTemplate.load(path)
        parties = {"Odwolujacy": [{"nip": "[NIP_1]"}], "Zamawiajacy": [{"nip": "[NIP_2]"}, {"nip": None}]}
        mapping = {"[NIP_1]": "012-345-67-89", "[NIP_2]": "000-111-22-33"}
        self.assertEqual(restore_markers(parties, mapping, template.formatters), {
            "Odwolujacy": [{"nip": "0123456789"}],
            "Zamawiajacy": [{"nip": "0001112233"}, {"nip": None}],
        })

    def test_transfer_accounts_restore_markers_and_only_remove_whitespace(self):
        template = DocumentTemplate.load(Path(__file__).resolve().parents[1] / "oczekiwane-json/przelew.jsonc")
        mapping = {"[PL_IBAN_1]": "GB82 WEST\n1234 5698 7654 32", "[PL_IBAN_2]": "00\t1234 5678 9012 3456 7890 1234"}
        for printed_prefix in ("PL ", ""):
            with self.subTest(printed_prefix=printed_prefix):
                text = "Odbiorca [PL_IBAN_1]\nNadawca " + printed_prefix + "[PL_IBAN_2]"
                client = Mock(spec=MistralClient)
                fields = dict.fromkeys(template.shape["przelew_bankowy"])
                fields.update(na_rachunek="[PL_IBAN_1]", z_rachunku=printed_prefix + "[PL_IBAN_2]")
                client.complete.return_value = json.dumps({"przelew_bankowy": fields})
                values = DocumentExtractor(client).extract_text(text, template, mapping)
                accounts = restore_markers(values, mapping, template.formatters)["przelew_bankowy"]
                self.assertEqual(accounts["na_rachunek"], "GB82WEST12345698765432")
                self.assertEqual(accounts["z_rachunku"], printed_prefix.strip() + "00123456789012345678901234")

    def test_transfer_title_removes_outer_quotes_and_only_the_period_after_them(self):
        path = Path(__file__).resolve().parents[1] / "oczekiwane-json/przelew.jsonc"
        template = DocumentTemplate.load(path)
        for original, expected in (
            ('„Opłata\n[NR_TRANSAKCJI_1]”.', 'Opłata TR123'),
            ('„Opłata”.', 'Opłata'),
            ('„Opłata”', 'Opłata'),
            ('"Opłata.".', 'Opłata.'),
            ('“Opłata”.', 'Opłata'),
            ('«Opis „Pakietu A”».', 'Opis „Pakietu A”'),
            ('Opłata „Pakiet A”.', 'Opłata „Pakiet A”.'),
            ('„Pakiet A” i „Pakiet B”.', '„Pakiet A” i „Pakiet B”.'),
            ('Opłata.', 'Opłata.'),
            ('„Opłata', '„Opłata'),
        ):
            with self.subTest(original=original):
                result = restore_markers(
                    {"przelew_bankowy": {"tytul": original}},
                    {"[NR_TRANSAKCJI_1]": "TR123"},
                    template.formatters,
                )
                self.assertEqual(result["przelew_bankowy"]["tytul"], expected)

    def test_transfer_date_is_normalized_after_marker_restoration(self):
        path = Path(__file__).resolve().parents[1] / "oczekiwane-json/przelew.jsonc"
        template = DocumentTemplate.load(path)
        for original in ("08.05.2026", "08-05-2026", "8/5/2026", "8 maja 2026", "2026-05-08"):
            with self.subTest(original=original):
                result = restore_markers(
                    {"przelew_bankowy": {"data_operacji": "[DATA_1]"}},
                    {"[DATA_1]": original},
                    template.formatters,
                )
                self.assertEqual(result["przelew_bankowy"]["data_operacji"], "2026-05-08")

        for value, expected in (
            (None, None),
            ("31.02.2026", "31.02.2026"),
            ("data\n  nieczytelna", "data nieczytelna"),
        ):
            with self.subTest(value=value):
                result = restore_markers({"przelew_bankowy": {"data_operacji": value}}, {}, template.formatters)
                self.assertEqual(result["przelew_bankowy"]["data_operacji"], expected)

    def test_reject_mismatched_input_before_sending(self):
        self.text.write_text("[PODMIOT_2]", encoding="utf-8")
        client = Mock(spec=MistralClient)
        with self.assertRaisesRegex(ValueError, "mapą dokumentu"):
            DocumentExtractor(client).extract(self.text, self.template)
        client.complete.assert_not_called()

    def test_model_selects_markers_with_original_scalar_examples(self):
        template = DocumentTemplate.parse("pelnomocnictwo", """// @normalize osoby.*.pesel digits
        {"osoby":[{"pesel":85120133547,"krs":null,"nazwa":"Przykładowa firma"}]}""")
        answers = {
            "osoby": [{"pesel": "[PESEL_1]", "krs": "[KRS_1]", "nazwa": "[PODMIOT_1]"}],
        }
        client = Mock(spec=MistralClient)
        client.complete.return_value = json.dumps(answers)
        mapping = {"[PESEL_1]": "01234567890", "[KRS_1]": "0000123456", "[PODMIOT_1]": "Firma z PDF"}
        document = " ".join(mapping)
        self.assertEqual(template.shape["osoby"][0]["pesel"], 85120133547)
        markers = DocumentExtractor(client).extract_text(document, template, mapping)
        self.assertEqual(markers, answers)
        self.assertEqual(restore_markers(markers, mapping, template.formatters), {
            "osoby": [{"pesel": "01234567890", "krs": "0000123456", "nazwa": "Firma z PDF"}],
        })
        client.complete.assert_called_once_with(template.prompt, document)

    def test_invented_marker_for_null_example_remains_null(self):
        template = DocumentTemplate.parse("przelew", '{"numer_transakcji":null}')
        client = Mock(spec=MistralClient)
        client.complete.return_value = '{"numer_transakcji":"[NR_TRANSAKCJI_2]"}'
        result = DocumentExtractor(client).extract_text(
            "[NR_TRANSAKCJI_1]", template, {"[NR_TRANSAKCJI_1]": "TR123"}
        )
        self.assertEqual(result, {"numer_transakcji": None})
        client.complete.assert_called_once()

import json
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from odwolania.cli import BatchProcessor, OutputPair
from odwolania.extraction import DocumentExtractor
from odwolania.mistral import RateLimitError
from odwolania.pipeline import ApiPacer, DocumentPipeline, main
from odwolania.templates import DocumentTemplate, TemplateRegistry


class TestBatch(TestCase):
    def test_processes_each_whole_document_and_writes_only_pairs(self) -> None:
        documents = []

        def pseudonymize(text: str) -> tuple[str, dict[str, str]]:
            documents.append(text)
            return text.replace("Anna", "[OSOBA_1]"), {"[OSOBA_1]": "Anna"}

        def read_text(path: Path) -> str:
            if path.stem == "awaria":
                raise RuntimeError("Uszkodzony PDF")
            return "Strona 1: Anna.\n\nStrona 2: Anna."

        with TemporaryDirectory() as root:
            input_dir, output_dir = Path(root) / "input", Path(root) / "output"
            (input_dir / "sprawa").mkdir(parents=True)
            for name in ("awaria.pdf", "ogłoszenie.PDF"):
                (input_dir / "sprawa" / name).touch()
            with self.assertLogs("odwolania", level="INFO") as logs:
                status = BatchProcessor(read_text, pseudonymize).run(input_dir, output_dir)
            self.assertEqual(status, 1)
            self.assertEqual(documents, ["Strona 1: Anna.\n\nStrona 2: Anna."])
            results = output_dir / "sprawa"
            self.assertEqual({file.name for file in results.iterdir()}, {"ogłoszenie.txt", "ogłoszenie.mapa.json"})
            self.assertEqual(
                (results / "ogłoszenie.txt").read_text(), "Strona 1: [OSOBA_1].\n\nStrona 2: [OSOBA_1]."
            )
            mapping = results / "ogłoszenie.mapa.json"
            self.assertEqual(json.loads(mapping.read_text()), {"[OSOBA_1]": "Anna"})
            self.assertEqual(stat.S_IMODE(mapping.stat().st_mode), 0o600)
            self.assertTrue(all("Anna" not in line for line in logs.output))

    def test_failed_text_publish_restores_previous_map(self) -> None:
        with TemporaryDirectory() as root:
            target = Path(root) / "dokument.txt"
            mapping = target.with_suffix(".mapa.json")
            OutputPair.write(target, "[OSOBA_1]", {"[OSOBA_1]": "Anna"})
            original_replace = Path.replace

            def fail_text_publish(path: Path, destination: Path) -> Path:
                if destination == target:
                    raise OSError("Symulowany błąd zapisu")
                return original_replace(path, destination)

            with patch.object(Path, "replace", fail_text_publish), self.assertRaises(OSError):
                OutputPair.write(target, "[OSOBA_1]", {"[OSOBA_1]": "Maria"})
            self.assertEqual(target.read_text(), "[OSOBA_1]")
            self.assertEqual(json.loads(mapping.read_text()), {"[OSOBA_1]": "Anna"})

    def test_appeal_pipeline_restores_locally_and_preserves_published_files_on_error(self) -> None:
        class FakeClient:
            def complete(self, template, document):
                return json.dumps({
                    "Odwolujacy": [{"nazwa": "[PODMIOT_1]"}],
                    "ZamowieniePubliczne": {
                        "numer_bzp": "[NR_BZP_1]", "numer_ted": "[NR_TED_1] [NR_TED_2]"
                    },
                })

        reader = Mock(return_value="ODWOŁANIE\nOryginalny dokument")
        pseudonymize = Mock(return_value=(
            "adres do korespondencji: [PODMIOT_1], [NR_BZP_1]\n[NR_TED_1]\n[NR_TED_2]",
            {
                "[PODMIOT_1]": "Przykładowa Kancelaria Spółka z ograniczoną\nodpowiedzialnością",
                "[NR_BZP_1]": "2026/BZP 00123456/01",
                "[NR_TED_1]": "2026/S",
                "[NR_TED_2]": "123-641651",
            },
        ))
        client = Mock(wraps=FakeClient())
        template = DocumentTemplate.parse("odwolanie", r"""// @match odwołanie
        // @normalize ZamowieniePubliczne.numer_bzp compact-upper
        // @normalize ZamowieniePubliczne.numer_ted ted
        {
          "Odwolujacy": [{"nazwa": "[PODMIOT]"}],
          "ZamowieniePubliczne": {"numer_bzp": "[NR_BZP]", "numer_ted": "[NR_TED]"}
        }""")
        pipeline = DocumentPipeline(
            BatchProcessor(reader, pseudonymize), TemplateRegistry((template,)), DocumentExtractor(client)
        )
        with TemporaryDirectory() as root:
            source = Path(root) / "input" / "sprawa" / "odwolanie.pdf"
            target = Path(root) / "output" / "sprawa" / "odwolanie.txt"
            self.assertEqual(pipeline.run([(source, target)]), 0)
            reader.assert_called_once_with(source)
            pseudonymize.assert_called_once_with("ODWOŁANIE\nOryginalny dokument")
            document, mapping = pseudonymize.return_value
            client.complete.assert_called_once_with(template.prompt, document)
            self.assertNotIn("@normalize", template.prompt)
            expected = {
                "Odwolujacy": [{"nazwa": "Przykładowa Kancelaria Spółka z ograniczoną odpowiedzialnością"}],
                "ZamowieniePubliczne": {
                    "numer_bzp": "2026/BZP00123456/01", "numer_ted": "641651-2026",
                },
            }
            output = target.with_suffix(".json")
            self.assertEqual(json.loads(output.read_text()), expected)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(json.loads(target.with_suffix(".mapa.json").read_text()), mapping)
            client.complete.reset_mock()
            client.complete.side_effect = OSError("Symulowany błąd połączenia")
            with self.assertLogs("odwolania", level="ERROR"):
                self.assertEqual(pipeline.run([(source, target)]), 1)
            client.complete.assert_called_once_with(template.prompt, document)
            self.assertEqual(json.loads(output.read_text()), expected)
            self.assertEqual(target.read_text(), document)
            self.assertEqual(json.loads(target.with_suffix(".mapa.json").read_text()), mapping)

    def test_batch_loads_added_type_and_preserves_relative_paths(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            input_dir = base / "input"
            output_dir = base / "output"
            templates = base / "oczekiwane-json"
            (input_dir / "sprawa").mkdir(parents=True)
            templates.mkdir()
            (templates / "odwolanie.jsonc").write_text('// @match odwołanie\n{"data": ""}', encoding="utf-8")
            (input_dir / "sprawa" / "dowolna-nazwa.PDF").touch()
            processor = BatchProcessor(Mock(return_value="Raport VAT\nKwota 12"), lambda text: (text, {}))
            client = Mock()
            client.complete.return_value = '{"kwota":12}'
            args = ["--input", str(input_dir), "--output", str(output_dir), "--templates", str(templates)]
            final = output_dir / "sprawa/dowolna-nazwa.json"
            with patch("odwolania.pipeline.local_pdf_processor", return_value=processor), patch(
                "odwolania.pipeline.MistralClient.from_environment", return_value=client
            ) as connect:
                self.assertEqual(main(args), 0)
                self.assertEqual(final.read_bytes(), b"{}")
                connect.assert_not_called()
                (templates / "raport_vat.jsonc").write_text('{"kwota": 0.0,}', encoding="utf-8")
                self.assertEqual(main(args + ["--model", "wybrany-model"]), 0)
                connect.assert_called_once_with("wybrany-model")
            self.assertEqual(json.loads(final.read_text()), {"kwota": 12})

    def test_unrecognized_and_ambiguous_pdfs_write_empty_object_without_api(self):
        registry = TemplateRegistry((
            DocumentTemplate.parse("pierwszy", '// @match tytuł\n{"pole": null}'),
            DocumentTemplate.parse("drugi", '// @match tytuł\n{"inne": ""}'),
        ))
        with TemporaryDirectory() as root, patch("odwolania.pipeline.MistralClient.from_environment") as client:
            for json_only in (False, True):
                with self.subTest(json_only=json_only):
                    processor = BatchProcessor(Mock(side_effect=["Ogłoszenie", "TYTUŁ"]), Mock())
                    pipeline = DocumentPipeline(processor, registry, json_only=json_only)
                    paths = [Path(root) / name for name in ("obcy.txt", "niejednoznaczny.txt")]
                    paths[0].with_suffix(".json").write_text('{"stary":"wynik"}')
                    paths[1].with_suffix(".json").write_bytes(b"")
                    self.assertEqual(pipeline.run([(target.with_suffix(".pdf"), target) for target in paths]), 0)
                    self.assertEqual({p.name for p in Path(root).iterdir()}, {"obcy.json", "niejednoznaczny.json"})
                    for target in paths:
                        self.assertEqual(target.with_suffix(".json").read_bytes(), b"{}")
                    processor.pseudonymize.assert_not_called()
            client.assert_not_called()

    def test_local_rule_takes_precedence_and_only_field_paths_reach_model(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            (base / "protokol.jsonc").write_text('{"numer": "", "opis": ""}')
            (base / "protokol.py").write_text(
                "class protokol:\n"
                "    def zastosuj(self, tekst, wynik):\n"
                "        wynik['numer'] = tekst.split('Numer: ')[1]\n"
            )
            registry = TemplateRegistry.load(base)
            reader = Mock(return_value="Protokol\nNumer: TAJNY-123")
            processor = BatchProcessor(reader, lambda raw: ("Protokol\nNumer: [NUMER_1]", {"[NUMER_1]": "TAJNY-123"}))
            client = Mock()
            client.complete.return_value = '{"numer":"[OBCY_9]", "opis":"Tekst  z modelu"}'
            pipeline = DocumentPipeline(processor, registry, DocumentExtractor(client))
            target = base / "wynik.txt"
            self.assertEqual(pipeline.run([(base / "dowolny.pdf", target)]), 0)
            self.assertEqual(json.loads(target.with_suffix(".json").read_text()), {
                "numer": "TAJNY-123", "opis": "Tekst z modelu",
            })
            client.complete.assert_called_once()
            prompt, document = client.complete.call_args.args
            self.assertEqual(document, "Protokol\nNumer: [NUMER_1]")
            self.assertIn('[["numer"]]', prompt)
            self.assertNotIn("TAJNY-123", str(client.mock_calls))

    def test_complete_local_rule_needs_no_api_or_template_registration(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            (base / "protokol.jsonc").write_text('// @normalize numer digits\n{"numer": ""}')
            (base / "protokol.py").write_text(
                "class protokol:\n"
                "    @staticmethod\n"
                "    def zastosuj(tekst, wynik):\n"
                "        wynik['numer'] = tekst.splitlines()[1]\n"
            )
            pipeline = DocumentPipeline(BatchProcessor(lambda path: "Protokol\n001 23", lambda raw: (raw, {})),
                                        TemplateRegistry.load(base))
            target = base / "wynik.txt"
            with patch("odwolania.pipeline.MistralClient.from_environment") as connect:
                self.assertEqual(pipeline.run([(base / "dowolny.pdf", target)]), 0)
                connect.assert_not_called()
            self.assertEqual(json.loads(target.with_suffix(".json").read_text()), {"numer": "00123"})

    def test_invalid_rule_contract_fails_at_startup(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            (base / "protokol.jsonc").write_text('{"numer": ""}')
            for code in ("class inna: pass", "class protokol: pass",
                         "class protokol:\n    def zastosuj(self, tekst): pass"):
                with self.subTest(code=code):
                    (base / "protokol.py").write_text(code)
                    with self.assertRaisesRegex(ValueError, r"protokol\.py"):
                        TemplateRegistry.load(base)

    def test_json_only_allows_a_pdf_named_like_another_documents_map(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            inputs, outputs, templates = (base / name for name in ("input", "output", "templates"))
            inputs.mkdir()
            templates.mkdir()
            for name in ("plik.PDF", "plik.mapa.pdf"):
                (inputs / name).touch()
            (templates / "raport.jsonc").write_text('{"wartosc":""}')
            processor = BatchProcessor(lambda path: "Raport" if path.stem == "plik" else "Instrukcja",
                                       lambda raw: ("Raport [OSOBA_1]", {"[OSOBA_1]": "Anna"}))
            client = Mock()
            client.complete.return_value = '{"wartosc":"[OSOBA_1]"}'
            args = ["--json-only", "--input", str(inputs), "--output", str(outputs), "--templates", str(templates)]
            with patch("odwolania.pipeline.local_pdf_processor", return_value=processor), patch(
                "odwolania.pipeline.MistralClient.from_environment", return_value=client
            ):
                self.assertEqual(main(args), 0)
            self.assertEqual({file.name for file in outputs.iterdir()}, {"plik.json", "plik.mapa.json"})
            self.assertEqual(json.loads((outputs / "plik.json").read_text()), {"wartosc": "Anna"})
            self.assertEqual((outputs / "plik.mapa.json").read_bytes(), b"{}")
            self.assertEqual(stat.S_IMODE((outputs / "plik.json").stat().st_mode), 0o600)
            client.complete.assert_called_once()

    def test_json_only_preserves_local_fields_on_first_api_failure_and_prior_result_on_rerun(self):
        with TemporaryDirectory() as root:
            directory = Path(root)
            template = DocumentTemplate.parse("raport", '{"kod":"", "opis":""}',
                                               rule=lambda raw, result: result.update(kod="001"))
            client = Mock()
            client.complete.side_effect = RuntimeError("HTTP 503")
            pipeline = DocumentPipeline(BatchProcessor(lambda path: "Raport", lambda raw: (raw, {})),
                                        TemplateRegistry((template,)), DocumentExtractor(client), json_only=True)
            job = directory / "skan.pdf", directory / "skan.txt"
            final = directory / "skan.json"
            with self.assertLogs("odwolania", level="ERROR"):
                self.assertEqual(pipeline.run([job]), 1)
            self.assertEqual(json.loads(final.read_text()), {"kod": "001", "opis": None})
            final.write_text('{"kod":"001","opis":"poprzedni wynik"}')
            with self.assertLogs("odwolania", level="ERROR"):
                self.assertEqual(pipeline.run([job]), 1)
            self.assertEqual(json.loads(final.read_text())["opis"], "poprzedni wynik")
            self.assertEqual(client.complete.call_count, 2)
            self.assertEqual(list(directory.iterdir()), [final])

    def test_api_pacing_observes_both_quotas_and_rechecks_after_another_workers_429(self):
        pacer = ApiPacer(15)
        now = 100
        waits = []

        def sleep(seconds):
            nonlocal now
            waits.append(seconds)
            now += seconds
            if len(waits) == 1:
                pacer.defer(3)

        with patch("odwolania.pipeline.time.monotonic", side_effect=lambda: now), patch(
            "odwolania.pipeline.time.sleep", side_effect=sleep
        ):
            pacer.wait()
            pacer.charge_tokens(10000, 100000)
            pacer.charge_tokens(5000, 100000)
            pacer.wait()
            pacer.wait()
        self.assertEqual(waits, [9, 3, 4])

    def test_429_defers_next_document_without_retrying_the_current_one(self):
        pacer = Mock()
        client = Mock()
        client.complete.side_effect = [RateLimitError(12), '{"pole":"wartość"}']
        template = DocumentTemplate.parse("raport", '{"pole":""}')
        with TemporaryDirectory() as root:
            pipeline = DocumentPipeline(BatchProcessor(lambda path: "Raport", lambda raw: (raw, {})),
                                        TemplateRegistry((template,)), DocumentExtractor(client), json_only=True,
                                        pacer=pacer)
            jobs = [(Path(root) / f"{n}.pdf", Path(root) / f"{n}.txt") for n in (1, 2)]
            with self.assertLogs("odwolania", level="ERROR"):
                self.assertEqual(pipeline.run(jobs), 1)
            self.assertEqual(client.complete.call_count, 2)
            self.assertEqual(pacer.wait.call_count, 2)
            pacer.defer.assert_called_once_with(12)
            self.assertEqual(json.loads((Path(root) / "2.json").read_text()), {"pole": "wartość"})

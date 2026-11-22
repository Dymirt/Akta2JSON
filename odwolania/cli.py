import argparse
import fcntl
import json
import logging
import os
import sys
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

LOG = logging.getLogger("odwolania")


def find_pdfs(input_dir: Path) -> list[Path]:
    return sorted(
        path for path in input_dir.rglob("*")
        if path.suffix.lower() == ".pdf" and path.is_file() and not path.is_symlink()
    )


class OutputPair:
    """Publish a text and map, optionally with the final JSON, under one lock."""

    @staticmethod
    def write(target: Path, text: str, mapping: dict[str, str], *, result: dict | None = None) -> None:
        mapping_target = target.with_suffix(".mapa.json")
        content = (
            (mapping_target, json.dumps(mapping, ensure_ascii=False, indent=2) + "\n"),
            (target, text),
        )
        if result is not None:
            final_json = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            content += ((target.with_suffix(".json"), final_json),)
        OutputPair._write(target.parent, content)

    @staticmethod
    def write_json(target: Path, result: dict, *, only_if_missing: bool = False) -> bool:
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n" if result else "{}"
        return OutputPair._write(target.parent, ((target.with_suffix(".json"), content),), only_if_missing=only_if_missing)

    @staticmethod
    def _write(parent: Path, content: tuple[tuple[Path, str], ...], *, only_if_missing: bool = False) -> bool:
        parent.mkdir(parents=True, exist_ok=True)
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(directory, fcntl.LOCK_EX)
            if only_if_missing and any(target.exists() for target, _ in content):
                return False
            OutputPair._publish(parent, content)
            return True
        finally:
            os.close(directory)

    @staticmethod
    def _publish(parent: Path, content: tuple[tuple[Path, str], ...]) -> None:
        with TemporaryDirectory(prefix=".odwolania-", dir=parent) as staging:
            workspace = Path(staging)
            prepared = []
            backups = {}
            for index, (target, text) in enumerate(content):
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise ValueError(f"Ścieżka wyniku nie wskazuje na zwykły plik: {target.name}")
                staged = workspace / str(index)
                descriptor = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(text)
                prepared.append((staged, target))
                if target.exists():
                    backup = workspace / f"previous-{index}"
                    copy2(target, backup)
                    backups[target] = backup

            published = []
            try:
                for staged, target in prepared:
                    staged.replace(target)
                    published.append(target)
            except OSError:
                for target in reversed(published):
                    if target in backups:
                        backups[target].replace(target)
                    else:
                        target.unlink(missing_ok=True)
                raise


class BatchProcessor:
    def __init__(self, read_text: Callable[[Path], str], pseudonymize: Callable[[str], tuple[str, dict[str, str]]]) -> None:
        self.read_text = read_text
        self.pseudonymize = pseudonymize

    def prepare(self, source: Path) -> tuple[str, dict[str, str]]:
        return self.pseudonymize(self.read_text(source))

    def run(self, input_dir: Path, output_dir: Path) -> int:
        output_dir = output_dir.resolve()
        sources = [path.relative_to(input_dir) for path in find_pdfs(input_dir)]
        collisions = Counter(path.with_suffix(".txt").as_posix().casefold() for path in sources)
        errors = 0
        for source in sources:
            relative_text = source.with_suffix(".txt")
            try:
                if collisions[relative_text.as_posix().casefold()] > 1:
                    raise ValueError(f"Więcej niż jeden PDF wskazuje na {relative_text}")
                target = output_dir / relative_text
                if not target.parent.resolve().is_relative_to(output_dir):
                    raise ValueError("Katalog wyniku znajduje się poza output")
                LOG.info("Odczytuję %s", source)
                text, mapping = self.prepare(input_dir / source)
                OutputPair.write(target, text, mapping)
                LOG.info("%s → %s i %s", source, relative_text, relative_text.with_suffix(".mapa.json"))
                LOG.debug("Liczba identyfikatorów w mapie: %d", len(mapping))
            except (OSError, RuntimeError, ValueError) as error:
                LOG.error("%s: %s", source, error)
                errors += 1
        LOG.info("Przetworzone: %d, błędy: %d", len(sources) - errors, errors)
        return 1 if errors else 0


def local_pdf_processor() -> BatchProcessor:
    from anon_legal_pl.anonimizuj import pseudonimizuj, zbuduj_analizator
    from anon_legal_pl.ocr import pdf_na_tekst
    from presidio_analyzer import Pattern, PatternRecognizer

    from .bank_accounts import FOREIGN_IBAN
    from .ocr_email import LabelledEmailRecognizer

    analyzer = zbuduj_analizator("pl_core_news_md")
    analyzer.registry.add_recognizer(LabelledEmailRecognizer())
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="PL_IBAN", supported_language="pl", global_regex_flags=0,
        patterns=[Pattern("foreign_iban", FOREIGN_IBAN.pattern, 1.0)],
    ))
    return BatchProcessor(pdf_na_tekst, partial(pseudonimizuj, analyzer=analyzer))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["extract"]:
        from .extraction import main as extract

        return extract(argv[1:])

    if argv[:1] == ["models"]:
        from .mistral import models_main

        return models_main(argv[1:])

    if argv and argv[0] in {"pipeline", "appeal"}:
        from .pipeline import main as pipeline

        return pipeline(argv[1:])

    parser = argparse.ArgumentParser(
        description="Lokalna pseudonimizacja pełnego tekstu dokumentów PDF",
        epilog="`odwolania models` wypisuje modele Mistral EU. Polecenia extract i pipeline obsługują --model.",
    )
    parser.add_argument("--input", type=Path, default=Path("input"), help="Katalog wejściowy PDF")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Katalog tekstów i map JSON")
    parser.add_argument("--verbose", action="store_true", help="Raportuj liczbę identyfikatorów w mapie")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    LOG.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    try:
        input_dir = args.input.resolve()
        output_dir = args.output.resolve()
        if not input_dir.is_dir():
            raise ValueError(f"Brak katalogu wejściowego: {input_dir}")
        if output_dir == input_dir:
            raise ValueError("Katalog wyników musi być oddzielony od input")
        output_dir.mkdir(parents=True, exist_ok=True)
        processor = local_pdf_processor()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        LOG.error("%s", error)
        return 2

    return processor.run(input_dir, output_dir)

"""Classify PDFs locally and extract the JSON defined for each recognized document."""

import argparse
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .cli import LOG, BatchProcessor, OutputPair, find_pdfs, local_pdf_processor
from .extraction import DocumentExtractor, format_result, restore_markers, validate_result
from .mistral import MistralClient, RateLimitError
from .rules import empty_result, field_values, set_fields
from .templates import DocumentTemplate, TemplateRegistry


class InferenceError(RuntimeError):
    """One API call failed. Keep local fields available for a first competition run."""

    def __init__(self, error, local_result):
        super().__init__(str(error))
        self.local_result = local_result


class ApiPacer:
    """Space request starts across this batch's worker processes."""

    def __init__(self, requests_per_minute):
        self.interval = 60.0 / requests_per_minute
        # Next available monotonic times for the request quota and the token quota.
        self.available = multiprocessing.Array("d", [0, 0])

    def wait(self):
        while True:
            with self.available.get_lock():
                now = time.monotonic()
                delay = max(self.available) - now
                if delay <= 0:
                    self.available[0] = now + self.interval
                    return
            time.sleep(delay)

    def defer(self, seconds):
        with self.available.get_lock():
            self.available[0] = max(self.available[0], time.monotonic() + seconds)

    def charge_tokens(self, cost, limit):
        with self.available.get_lock():
            self.available[1] = max(self.available[1], time.monotonic()) + 60 * cost / limit


class DocumentPipeline:
    def __init__(
        self,
        pdf_processor: BatchProcessor,
        registry: TemplateRegistry,
        extractor: DocumentExtractor | None = None,
        *, model: str | None = None, json_only: bool = False, pacer: ApiPacer | None = None,
    ):
        self.pdf_processor = pdf_processor
        self.registry = registry
        self.extractor = extractor
        self.model = model
        self.json_only = json_only
        self.pacer = pacer

    def _process(self, source: Path, target: Path) -> None:
        raw = self.pdf_processor.read_text(source)
        template = self.registry.classify(raw)
        if template is None:
            OutputPair.write_json(target, {})
            LOG.info("Brak jednoznacznego typu, zapisano {} w %s", target.with_suffix(".json"))
            return

        text, mapping = self.pdf_processor.pseudonymize(raw)
        try:
            result = self._extract(raw, text, mapping, template)
        except InferenceError as error:
            if self.json_only and OutputPair.write_json(target, error.local_result, only_if_missing=True):
                LOG.warning("Zapisano częściowy wynik reguł dla %s", source)
            raise
        if self.json_only:
            OutputPair.write_json(target, result)
        else:
            OutputPair.write(target, text, mapping, result=result)
        LOG.info("Zapisano %s (%s)", target.with_suffix(".json"), template.name)

    def _extract(self, raw: str, text: str, mapping: dict, template: DocumentTemplate) -> dict:
        result = empty_result(template.shape)
        template.apply_rules(raw, result)
        if template.rule:
            validate_result(template.shape, result, template.formatters)
        fields = dict(field_values(result))
        # The model identifies list entries, including the people to whom local rules may then apply.
        fixed = {path: value for path, value in fields.items() if value is not None and not isinstance(value, list)}
        if len(fixed) < len(fields):
            if self.extractor is None:
                client = MistralClient.from_environment(self.model)
                if self.pacer:
                    client.on_token_usage = self.pacer.charge_tokens
                self.extractor = DocumentExtractor(client)
                LOG.info("Ekstrakcja przez Mistral EU, model %s.", client.model)
            try:
                if self.pacer:
                    self.pacer.wait()
                markers = self.extractor.extract_text(text, template, mapping, local_fields=tuple(fixed))
            except (OSError, RuntimeError) as error:
                if self.pacer and isinstance(error, RateLimitError):
                    self.pacer.defer(error.retry_after)
                local_result = format_result(result, template.formatters)
                raise InferenceError(error, local_result) from error
            result = restore_markers(markers, mapping)
            set_fields(result, fixed)
            template.apply_rules(raw, result)
        result = format_result(result, template.formatters)
        return validate_result(template.shape, result, template.formatters)

    def process_job(self, job: tuple[Path, Path]) -> int:
        source, target = job
        try:
            LOG.info("Odczytuję %s", source)
            self._process(source, target)
            return 0
        except (OSError, RuntimeError, ValueError) as error:
            LOG.error("%s: %s", source, error)
            return 1

    def run(self, jobs: list[tuple[Path, Path]]) -> int:
        return _batch_status(len(jobs), sum(map(self.process_job, jobs)))


def _batch_status(count, errors):
    LOG.info("Przetworzone: %d, błędy: %d", count - errors, errors)
    return int(bool(errors))


# Each process loads its own spaCy analyzer once. Only paths cross process boundaries.
_worker_pipeline: DocumentPipeline


def _init_worker(templates, model, json_only, pacer):
    global _worker_pipeline
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    LOG.setLevel(logging.INFO)
    _worker_pipeline = DocumentPipeline(local_pdf_processor(), TemplateRegistry.load(templates),
                                        model=model, json_only=json_only, pacer=pacer)


def _process_job(job):
    return _worker_pipeline.process_job(job)


def _jobs(paths, input_dir, output_dir, *, json_only=False):
    jobs = []
    targets = set()
    for path in paths:
        source = path.resolve()
        if path.is_symlink() or not source.is_relative_to(input_dir) or not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError(f"Podaj istniejący PDF w katalogu wejściowym: {path}")
        target = output_dir / source.relative_to(input_dir).with_suffix(".txt")
        files = {target.with_suffix(".json").as_posix().casefold()}
        if not json_only:
            files.update(file.as_posix().casefold() for file in (target, target.with_suffix(".mapa.json")))
        if targets & files or not target.parent.resolve().is_relative_to(output_dir):
            raise ValueError(f"Nieprawidłowa lub powtórzona ścieżka wyniku: {target}")
        targets.update(files)
        jobs.append((source, target))
    return jobs


def main(argv):
    parser = argparse.ArgumentParser(prog="odwolania pipeline", description="Rozpoznaj PDF-y i zapisz wyniki JSON")
    parser.add_argument("pdf", type=Path, nargs="*", help="Wybrane PDF-y. Domyślnie całe drzewo input.")
    parser.add_argument("--input", type=Path, default=Path("input"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--templates", type=Path, default=Path("oczekiwane-json"))
    parser.add_argument("--model", help="Identyfikator modelu Mistral. Nadpisuje MISTRAL_MODEL.")
    parser.add_argument("--json-only", action="store_true", help="Zapisuj tylko konkursowe JSON-y.")
    parser.add_argument("--workers", type=int, default=1, help="Liczba równolegle przetwarzanych dokumentów.")
    parser.add_argument("--api-rpm", type=int, default=15, help="Łączny limit żądań modelu na minutę (domyślnie 15).")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    LOG.setLevel(logging.INFO)
    try:
        input_dir, output_dir = args.input.resolve(), args.output.resolve()
        if not input_dir.is_dir():
            raise ValueError(f"Brak katalogu wejściowego: {input_dir}")
        if input_dir == output_dir:
            raise ValueError("Katalog wyników musi być oddzielony od wejściowego.")
        if args.workers < 1:
            raise ValueError("Liczba procesów musi być dodatnia.")
        if args.api_rpm < 1:
            raise ValueError("Limit żądań API na minutę musi być dodatni.")
        jobs = _jobs(args.pdf or find_pdfs(input_dir), input_dir, output_dir, json_only=args.json_only)
        registry = TemplateRegistry.load(args.templates)
        if not jobs:
            return _batch_status(0, 0)
        pacer = ApiPacer(args.api_rpm)
        if args.workers > 1 and len(jobs) > 1:
            with ProcessPoolExecutor(max_workers=min(args.workers, len(jobs)), initializer=_init_worker,
                                     initargs=(args.templates, args.model, args.json_only, pacer)) as pool:
                return _batch_status(len(jobs), sum(pool.map(_process_job, jobs)))
        pdf_processor = local_pdf_processor()
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        LOG.error("%s", error)
        return 2
    return DocumentPipeline(pdf_processor, registry, model=args.model, json_only=args.json_only, pacer=pacer).run(jobs)

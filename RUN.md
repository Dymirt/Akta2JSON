# Odwołania2JSON na VM UZP

## Komenda dla oceniających

Uruchom poniższe polecenie jako administrator w katalogu `/opt/solution`.

```sh
docker compose run --rm -T --user 0:0 pipeline --workers 2 --json-only --api-rpm 15 --model mistral-small-2603
```

Komenda czyta wszystkie PDF-y z drzewa `/opt/solution/input` i zapisuje po jednym pliku `.json` pod odpowiadającą ścieżką w `/opt/solution/output`. Dla dokumentu nierozpoznanego lub pasującego do kilku klas zapisuje pusty obiekt JSON `{}`. Po zakończeniu kontener wypisuje podsumowanie i kończy proces. Kod wyjścia `0` oznacza sukces, `1` błąd co najmniej jednego dokumentu, a `2` błąd uruchomienia. Jeśli wywołanie API zawiedzie przy pierwszym przetwarzaniu dokumentu, program zapisze jego lokalnie ustalone pola i zgłosi błąd. Pozostałe pliki w partii są dalej przetwarzane.

## Przygotowanie przez zespół przed oceną

Na VM z wdrożeniem CI/CD obraz, kod i wzorce są przypięte do tego samego commita. Identyfikator wydania pokazuje `readlink /opt/solution/.releases/current`. Oceniającym wystarczy komenda podana wyżej. [Instrukcja wdrożenia](deploy/README.md)

Przy instalacji ręcznej na nowej VM wykonaj następujące kroki.

1. Umieść bezpośrednio w `/opt/solution` pliki `RUN.md`, `Dockerfile`, `.dockerignore`, `compose.yaml`, `requirements.txt` oraz katalogi `odwolania/` i `oczekiwane-json/`. Użyj istniejących katalogów `input/` oraz `output/`. Dane treningowe i ich etykiety służą do testów zespołu.
2. W `/opt/solution/.env` zapisz `MISTRAL_API_KEY=<klucz zespołu>` z aktywnym limitem API na czas oceny i nadaj plikowi uprawnienia `0600`. Compose przekazuje klucz do kontenera. Polecenie oceny jawnie wybiera model, również gdy plik `.env` zawiera własne `MISTRAL_MODEL`.
3. Z katalogu `/opt/solution` wykonaj `docker compose build cli`. Obraz zawiera Python 3.13, Tesseract z językiem polskim oraz model spaCy. Zachowaj zbudowany obraz `hacknation2026-cli` na dysku VM. Polecenie oceny korzysta z lokalnego obrazu i uruchamia samodzielny kontener.
4. Sprawdź dostęp do modelu poleceniem `docker compose run --rm -T llm models | grep -Fx mistral-small-2603`. Do próby umieść w pustym `input/` po jednym odwołaniu, pełnomocnictwie, potwierdzeniu przelewu i dokumencie negatywnym, w tym skan. Zacznij z pustym `output/`. Wykonaj komendę dla oceniających, sprawdź jej kod wyjścia, liczbę i zawartość plików oraz czas. Usuń z obu katalogów własne pliki próbne przed przekazaniem VM. Limit całej partii wynosi 60 minut na 150 PDF-ów, czyli średnio 24 sekundy na PDF. [Komunikat organizatora z 22 listopada](USTALENIA-UZP.md#limit-czasu-na-przetworzenie-partii)

## Usługa zewnętrzna

Oba procesy dzielą limit 15 żądań na minutę. Program uwzględnia koszt tokenów i minutowy limit zwracany przez API. Po HTTP 429 stosuje czas oczekiwania dostawcy przed wysłaniem kolejnych dokumentów.

OCR, klasyfikacja i reguły działają na CPU. Dokument wymagający uzupełnienia pól przez model powoduje jedno żądanie do API Mistral AI pod adresem `https://api.eu.mistral.ai/v1`. Żądanie zawiera pełny pseudonimizowany tekst, wzorzec oraz ścieżki już ustalonych pól. Mapa danych źródłowych pozostaje w pamięci kontenera. Model `mistral-small-2603` (Mistral Small 4) ma licencję Apache 2.0, 119 mld parametrów łącznie i 6,5 mld aktywnych. [Karta modelu](https://docs.mistral.ai/models/mistral-small-4-0-26-03)

UZP wymaga serwerów w UE lub EOG. Mistral podaje dla regionalnej inferencji lokalizacje w UE i EFTA. EFTA obejmuje także Szwajcarię, która jest poza EOG. Przed oceną zespół powinien potwierdzić z dostawcą lokalizację przetwarzania dla swojego konta i modelu. Zasady przetwarzania Mistral opisuje w polityce prywatności oraz, dla klientów biznesowych, w umowie powierzenia. [Regiony inferencji](https://docs.mistral.ai/inference/regional-inference) · [Polityka prywatności](https://legal.mistral.ai/terms/privacy-policy/) · [Umowa powierzenia](https://legal.mistral.ai/terms/data-processing-addendum/)

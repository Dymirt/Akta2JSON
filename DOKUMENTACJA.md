# Dokumentacja techniczna Odwołania2JSON

Komendę konkursową i przygotowanie maszyny opisuje [instrukcja uruchomienia na VM UZP](RUN.md).

## Lokalny odczyt i pseudonimizacja

Umieść PDF-y w `input/`, opcjonalnie w podkatalogach. Uruchom `docker compose run --build --rm cli` z katalogu projektu. Po zbudowaniu obrazu wystarczy `docker compose run --rm cli`. Tesseract, polski model spaCy i biblioteki Pythona są częścią obrazu. Ta usługa działa bez sieci na CPU.

Dla `input/sprawa/dokument.pdf` otrzymasz dwa pliki w tym samym katalogu wynikowym.

- `output/sprawa/dokument.txt` zawiera cały tekst po zamianie wykrytych wartości na znaczniki, np. `[OSOBA_1]`.
- `output/sprawa/dokument.mapa.json` przechowuje znaczniki i oryginalne wartości. Identyfikatory są przypisane osobno w każdym PDF-ie.

Mapa zawiera dane źródłowe. CLI nadaje obu plikom uprawnienia `0600`. `--verbose` raportuje liczbę podstawień. Przy błędzie pojedynczego pliku CLI przetwarza resztę partii i kończy kodem `1`. Błędna konfiguracja daje kod `2`.

Maskowanie obejmuje wykryte tytuły zamówień, numery spraw (także w tytułach przelewów), numery ogłoszeń BZP i TED oraz adresy, w tym adres KIO. Rachunki są maskowane także bez `PL` i po rozbiciu na wiersze. Zapis 24-cyfrowy jest wykrywany przy etykiecie rachunku. Numery w formacie `CEN` i 13 cyfr oraz inne identyfikatory wykryte przy etykiecie transakcji lub operacji są maskowane również przy powtórzeniach. Numery wpisów zawodowych są maskowane przy etykiecie „nr wpisu”. Dodatkowy lokalny moduł Presidio rozpoznaje fragmenty przypominające uszkodzony adres w rubryce e-mail po OCR i maskuje ich powtórzenia. Mapa zachowuje oryginalny zapis wraz z błędami OCR.

Jeśli katalog wynikowy wymaga UID i GID właściciela hosta, uruchom polecenie z tymi identyfikatorami.

```sh
ODWOLANIA_UID="$(id -u)" ODWOLANIA_GID="$(id -g)" docker compose run --rm cli
```

## Od PDF do końcowego JSON-u

Po zbudowaniu obrazu poleceniem `docker compose build cli` ustaw `MISTRAL_API_KEY` w środowisku lub w pliku `.env` obok `compose.yaml`. Umieść PDF-y w `input/` i uruchom pipeline.

```sh
docker compose run --rm -T pipeline
```

Domyślnie przetwarza całe drzewo `input/`. Podaj ścieżki po nazwie usługi, jeśli chcesz wybrać konkretne PDF-y. Katalog wejściowy można podmienić przez `ODWOLANIA_INPUT`.

Klient używa regionalnego adresu `MISTRAL_BASE_URL=https://api.eu.mistral.ai/v1`. Mistral opisuje lokalizację inferencji jako UE i EFTA. Wymóg UZP obejmuje UE lub EOG, więc dla konkretnego wdrożenia trzeba potwierdzić lokalizację u dostawcy. [Regiony inferencji Mistrala](https://docs.mistral.ai/inference/regional-inference)

Domyślnym modelem jest `ministral-8b-2512` (Ministral 3 8B Instruct 2512, Apache 2.0). Dla lokalnych eksperymentów możesz ustawić `MISTRAL_MODEL` w `.env` albo przekazać `--model` do `pipeline` lub `llm extract`. Opcja `--model` ma pierwszeństwo. [Karta modelu](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512)

Dostępne dla swojego klucza modele czatu w regionie europejskim wyświetlisz poleceniem

```sh
docker compose run --rm -T llm models
```

Pipeline rozpoznaje odwołania, pełnomocnictwa i potwierdzenia przelewu. Lokalna reguła odczytuje jednoznaczne pola z tekstu PDF-u. Jeśli wypełni wszystkie pola, pipeline zapisuje wynik lokalnie. Gdy potrzebna jest ekstrakcja przez model, pipeline wysyła dokładnie jedno żądanie HTTP dla tego dokumentu. Zawiera ono pełny pseudonimizowany tekst, wzorzec JSONC i ścieżki pól już ustalonych lokalnie. Model ma zwrócić dla tych ścieżek `null`. Pipeline sprawdza odpowiedź i łączy poprawne wartości z wynikiem reguł. Mapa znaczników i ich oryginalnych wartości pozostaje na maszynie przetwarzającej PDF.

Rozpoznany `input/sprawa/dokument.pdf` daje `output/sprawa/dokument.json` oraz pliki `dokument.txt` i `dokument.mapa.json`. Dokument nieznanego typu lub pasujący do kilku typów daje plik `dokument.json` zawierający dokładnie `{}`. W obu polach rachunku przelewu wynik zachowuje kod kraju, jeśli widnieje w PDF-ie, i usuwa białe znaki. Pliki wynikowe mają uprawnienia `0600`. Opcja konkursowa `--json-only` zapisuje tylko wynikowy JSON. Opcja `--workers 2` pozwala dwóm procesom równolegle przetwarzać niezależne dokumenty. Każdy proces ładuje analizator jeden raz. Procesy wspólnie ograniczają tempo żądań przez `--api-rpm` (domyślnie 15). Uwzględniają też koszt i minutowy limit tokenów z odpowiedzi Mistrala oraz `Retry-After` z HTTP 429. Po takim błędzie odstęp dotyczy kolejnych dokumentów w partii.

### Dodawanie typu dokumentu

Dodaj jeden plik `.jsonc` do [oczekiwane-json](oczekiwane-json/). Compose montuje ten katalog, a pipeline odczytuje go na początku każdego uruchomienia. Nazwa pliku określa identyfikator typu, obiekt JSONC określa strukturę wyniku, a komentarze opisują pola dla modelu.

Przykładowy plik `protokol.jsonc` może wyglądać tak.

```jsonc
// @match protokół odbioru(?: robót)?
{
  "protokol": {
    // Data podpisania protokołu, w formacie YYYY-MM-DD.
    "data": "",
    // Wykonawca wskazany w nagłówku protokołu.
    "wykonawca": "Przykładowe Przedsiębiorstwo"
  }
}
```

Każda dyrektywa `@match` to wyrażenie regularne dopasowywane do całego wiersza wśród pierwszych 50 niepustych wierszy dokumentu, z pominięciem wielkości liter. Kilka dyrektyw to warianty alternatywne. Bez dyrektywy nagłówek wynika z nazwy pliku, z zamianą podkreśleń i łączników na spacje.

Dyrektywa `// @singleton pelnomocnicy pełnomocnik` pozwala odzyskać pojedynczy obiekt `pełnomocnik` jako jeden element listy. Przy odzyskiwaniu pól pierwszeństwo ma klucz ze wzorca, a następnie jego jednoznaczny wariant pisowni, np. `pełnomocnicy`. Dotyczy to również pustej listy. Każdy odzyskany rekord przechodzi walidację pól i znaczników, a wynik zawsze używa nazwy `pelnomocnicy`.

W końcowym JSON-ie pipeline automatycznie zastępuje ciągi białych znaków (w tym podziały wierszy) pojedynczą spacją i usuwa odstępy z obu końców każdej wartości tekstowej. Opcjonalne `@normalize ścieżka format` określa dodatkowe formatowanie pola po odtworzeniu wartości z mapy. Format `bank-account` usuwa z rachunku białe znaki i zachowuje kod kraju podany w dokumencie. Pozostałe formaty to `digits`, `spaces`, `compact-upper`, `ted`, `date-iso` (`YYYY-MM-DD`) i `transfer-title` (spacje oraz zewnętrzny cudzysłów tytułu przelewu). Znak `*` w ścieżce obejmuje elementy tablicy. Katalog wzorców można nadpisać przez `ODWOLANIA_TEMPLATES`.

Dyrektywa `@normalize pelnomocnicy.*.imie_nazwisko given-name-initial` poprawia małą pierwszą literę samodzielnego imienia przed nazwiskiem rozpoczynającym się wielką literą, po odtworzeniu wartości z mapy. Format `date-iso` zwraca `null` przy dacie niepełnej lub niemożliwej kalendarzowo.

### Opcjonalne reguły w Pythonie

Obok `protokol.jsonc` możesz dodać `protokol.py` z klasą `protokol` i metodą `zastosuj(tekst, wynik)`. Pipeline wczyta klasę przy następnym uruchomieniu, bez rejestracji i przebudowy obrazu. Moduł jest wykonywalnym kodem aplikacji. Powinien pochodzić z zaufanego katalogu wzorców. Sam plik JSONC wystarcza do ekstrakcji przez model.

Reguła dostaje surowy tekst całego PDF-u i modyfikuje słownik `wynik` w miejscu. Przy pierwszym wywołaniu pola skalarne mają wartość `None`, a listy są puste. Po ekstrakcji przez model reguła dostaje także odtworzone rekordy list. Dzięki temu może przypisać np. NIP właściwemu mocodawcy. Reguła powinna dawać ten sam wynik przy ponowieniu, wpisywać wartości tylko przy jednoznacznym źródle i zachowywać strukturę wzorca. Pusty wynik wyszukiwania pozostawia pole do ekstrakcji przez model.

Znaczenie pól określają trzy [oryginalne wzorce UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796/oczekiwane-json/). Kod rozpoznaje poniższe przypadki w tekście dokumentu.

| Typ | Co ustala kod |
| --- | --- |
| [Odwołanie](oczekiwane-json/odwolanie.py) | Odczytuje datownik, tytuł zamówienia i numer TED. Rozdziela sklejoną listę pełnomocników. Kod i opis czynności ustala z pierwszego zarzutu i wykazu czynności albo z pojedynczego datowanego zdania wprowadzającego ten zarzut. W skanach czyta też datę i rodzaj pierwszej pozycji numerowanego wykazu zaskarżonych czynności. Przy uszkodzonym separatorze e-maila pełnomocnika sprawdza adres w jego rubryce kontaktowej. Listę zamawiających, ich identyfikatory oraz role ustala model na podstawie instrukcji we wzorcu JSONC. |
| [Pełnomocnictwo](oczekiwane-json/pelnomocnictwo.py) | KRS, NIP i typ z oznaczonej sekcji jedynego mocodawcy. Przy zgodnym KRS i NIP kod oddziela adres od nazwy spółki wskazanej w deklaracji. Z kompletnego bloku podpisów przypisuje osoby do właściwych mocodawców. Osobno rozpoznaje podpis przyjęcia pełnomocnictwa i stanowisko pod nazwiskiem. |
| [Przelew](oczekiwane-json/przelew.py) | Datę operacji, kwotę w PLN, rachunki nadawcy i odbiorcy oraz numer transakcji. W skanach uwzględnia źródłową i docelową stronę transakcji, kolumny formularza oraz znak obciążenia konta. Tytuł odczytuje z cytatu lub z oznaczonej rubryki do następnej etykiety. Przy niecytowanym tytule rozbitym na wiersze potwierdza końcowy identyfikator w osobnym polu transakcji. |

### Ekstrakcja z gotowego tekstu

Aby uzyskać na stdout sam JSON ze znacznikami z już spseudonimizowanego odwołania, uruchom osobny etap ekstrakcji.

```sh
docker compose run --rm -T llm extract --model ministral-8b-2512 output/przyklad_04/odwolanie.txt oczekiwane-json/odwolanie.jsonc
```

Polecenie `llm extract` wysyła jedno żądanie HTTP z pełnym pseudonimizowanym tekstem i wzorcem JSONC. Sprawdza składnię odpowiedzi, klucze, typy pól, elementy list i znaczniki. Wypisuje na stdout JSON ze znacznikami, które odpowiadają wartościom z lokalnej mapy.

Po błędzie walidacji CLI odzyskuje **lokalnie z tej samej odpowiedzi** poprawne pola i rekordy list. Jeśli struktura odpowiedzi uniemożliwia odzyskanie jakiejkolwiek wartości, wynikiem ekstrakcji jest szkielet wzorca z `null` w polach skalarnych i pustymi listami. W pełnym przebiegu `pipeline` wpisuje do niego także wartości ustalone regułami. Oryginalne wartości znaczników odtwarza lokalnie przed zapisem.

Docker instaluje przez pip oficjalny pakiet `mistralai` w wersji przypiętej w `requirements.txt`. Ekstrakcja używa `client.chat.complete(...)` w trybie JSON, a polecenie `llm models` pobiera listę modeli przez `client.models.list()`. Obie operacje korzystają z regionu `eu`. Po błędzie HTTP klient zgłasza status bez ponawiania żądania. Polecenie `llm extract` zwraca kod `1`, a `pipeline` przetwarza pozostałe pliki i kończy partię kodem `1`. Gdy połączenie z API się nie powiedzie podczas pierwszego przebiegu `--json-only`, rozpoznany dokument otrzymuje częściowy JSON z lokalnie ustalonymi polami. Przy ponowieniu błąd połączenia zachowuje już opublikowany wynik. [Oficjalny SDK Mistrala dla Pythona](https://pypi.org/project/mistralai/2.10.1/)

## Modele używane przy ekstrakcji i pseudonimizacji

W komendzie z `RUN.md` działa jeden generatywny LLM, Ministral 3 8B Instruct 2512. Biblioteka `anon-legal-pl` pseudonimizuje dokument lokalnie przez Presidio i polski model rozpoznawania nazw własnych spaCy `pl_core_news_md`. Skany odczytuje lokalny Tesseract. Fork oferuje również drugi przebieg pseudonimizacji z Bielikiem 11B przez Ollamę. Wymaga on opcji `--bielik` w osobnym skrypcie. Komenda konkursowa i porównanie modeli korzystają ze ścieżki spaCy. [Wywołanie w projekcie](odwolania/cli.py) · [Opcja Bielika w przypiętym forku](https://github.com/Dymirt/anon-legal-pl/blob/ed24629fd3a4d81f114390bebffcbc22d31e632c/anonimizuj.py#L69-L77)

W tabeli podano średnią arytmetyczną liczby parametrów wszystkich generatywnych LLM w danym wariancie, w miliardach. Każdy model ekstrakcji oceniano osobno. Dwie ostatnie kolumny pokazują hipotetyczne włączenie Bielika (11,169 mld) jako drugiego LLM. Punkty obliczono według tabeli z 21 listopada, którą UZP następnie wycofał. Aktualne publiczne README zapowiada nowe wytyczne. [Zmiana zasad UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/commit/519b26c6be0120144c43529b29ec73d441b836b1) · [Kryteria UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026#sposób-punktacji-llm)

| Model ekstrakcji | Średnia w teście F1 | Punkty wg dawnej tabeli | Średnia z dodatkowym Bielikiem | Punkty wg dawnej tabeli |
| --- | ---: | ---: | ---: | ---: |
| Ministral 3B 2512 | 3,849 mld | 20 | 7,509 mld | 20 |
| Ministral 8B 2512 | 8,918 mld | 18 | 10,043 mld | 18 |
| Ministral 14B 2512 | 13,945 mld | 18 | 12,557 mld | 18 |
| Mistral Small 4 | ok. 119 mld | 4 | ok. 65,084 mld | 8 |

Ministral 14B wykorzystany w szybkim porównaniu ma 13 945 031 680 parametrów. Wyniki dla skanów i dokumentów cyfrowych opisano osobno. [Wagi producenta](https://huggingface.co/api/models/mistralai/Ministral-3-14B-Instruct-2512-BF16) · [Pomiar na 36 PDF-ach](tests/porownanie-modeli.md#szybkie-porównanie-modeli-do-14-mld-parametrów)

Liczby Ministrali pochodzą z opublikowanych wag BF16. Dla Small 4 uwzględniono 119 mld parametrów całego modelu MoE. Producent podaje też 6,5 mld parametrów aktywnych. [Wagi Ministral 3B](https://huggingface.co/api/models/mistralai/Ministral-3-3B-Instruct-2512-BF16) · [Wagi Ministral 8B](https://huggingface.co/api/models/mistralai/Ministral-3-8B-Instruct-2512-BF16) · [Karta Small 4](https://docs.mistral.ai/models/mistral-small-4-0-26-03) · [Wagi Bielika](https://huggingface.co/api/models/speakleash/Bielik-11B-v2.3-Instruct)

## Kod źródłowy

Docker instaluje [fork Dymirt/anon-legal-pl](https://github.com/Dymirt/anon-legal-pl/commit/ed24629fd3a4d81f114390bebffcbc22d31e632c) na licencji Apache-2.0. `Dockerfile` przypina commit i sumę SHA-256 jego archiwum. CLI korzysta z API forka do OCR i generowania znaczników z mapą oraz z modelu [pl_core_news_md](https://github.com/explosion/spacy-models/releases/tag/pl_core_news_md-3.8.0). Przy nakładaniu się wyników reguły formatów mają pierwszeństwo przed dopasowaniami modelu. Wynik zależy od jakości OCR i skuteczności detekcji. Przed udostępnieniem tekstu przejrzyj go pod kątem pozostałych danych.

## Przekazanie kodu i gotowego obrazu

Do commita dołącz kod, wzorce z regułami, `RUN.md`, `Dockerfile`, `compose.yaml` i `requirements.txt`. Obraz zawiera zainstalowane pakiety i model, a źródła oraz licencja biblioteki są w forku. Dokumenty wejściowe, wyniki i mapy podstawień trzymaj poza commitem i archiwum obrazu.

Repozytorium projektu jest dostępne na [GitHubie](https://github.com/Dymirt/Akta2JSON). GitHub Actions buduje obraz i uruchamia testy dla zmian kierowanych do `main`. W okresie dostępu zespołu VM pobiera nowe commity z tej gałęzi, sprawdza je w izolowanym kontenerze i aktywuje wydanie po zaliczeniu testów. Klucz Mistrala przekaż na VM przez SSH. [Konfiguracja i weryfikacja CI/CD](deploy/README.md)

Na VM możesz zbudować obraz bezpośrednio przed oceną zgodnie z `RUN.md`. Przy przenoszeniu obrazu z innego komputera przygotuj wariant `linux/amd64`.

```sh
docker buildx build --platform linux/amd64 --load -t odwolania2json:uzp-amd64 .
docker image save -o odwolania2json-amd64.tar odwolania2json:uzp-amd64
```

Na VM wczytaj archiwum i nadaj obrazowi nazwę używaną przez Compose. Po umieszczeniu kodu, konfiguracji i wzorców w `/opt/solution` wykonaj próbę opisaną w [RUN.md](RUN.md).

```sh
docker image load -i odwolania2json-amd64.tar
docker image tag odwolania2json:uzp-amd64 hacknation2026-cli
```

Przy publikacji obrazu sprawdź warunki redystrybucji, w tym udostępniania źródeł. PyMuPDF jest dostępny na AGPLv3 lub licencji komercyjnej, a model `pl_core_news_md` na GPLv3. [Licencjonowanie Artifex](https://artifex.com/licensing) · [Licencja modelu spaCy](https://github.com/explosion/spacy-models/releases/tag/pl_core_news_md-3.8.0)

## Uruchamianie testów i pomiar reguł

```sh
python3.13 -m unittest discover -s tests -v
```

Wszystkie testy, w tym regresje wymagające polskiego modelu, uruchomisz w zbudowanym obrazie.

```sh
docker compose run --rm -T -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/oczekiwane-json:/app/oczekiwane-json:ro" --entrypoint python cli \
  -m unittest discover -s tests -v
```

Do lokalnego pomiaru pobierz repozytorium UZP do katalogu `hacknation-2026/` w rewizji `eadffbc`. Skrypt czyta wszystkie 228 opublikowanych PDF-ów. Osobno raportuje klasyfikację 180 cyfrowych dokumentów z etykietami, 30 numerowanych skanów, jednego skanu z szablonu i 17 negatywów. Dla nowych skanów liczy precyzję, czułość i mikro-F1 niepustych wartości skalarnych zgodnych co do ścieżki i wartości z etykietą. Skan z szablonu ma wyłącznie znaną klasę. [Skrypt pomiarowy](tests/sprawdz_reguly.py)

```sh
docker compose run --rm -T -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/hacknation-2026:/app/materialy:ro" \
  -v "$PWD/oczekiwane-json:/app/oczekiwane-json:ro" --entrypoint python cli \
  -m tests.sprawdz_reguly /app/materialy /app/oczekiwane-json
```

Aby sprawdzić również reguły zależne od rozpoznania mocodawców, między ostatnimi dwoma argumentami podaj katalog archiwalnych wyników AI zawierający `przyklad_01/pelnomocnictwo.json`–`przyklad_60/pelnomocnictwo.json`. Skrypt pobierze z nich tylko nazwy i listy mocodawców do oceny reguł w 60 cyfrowych sprawach. Na nowych skanach reguły zawsze startują od pustego szkieletu.

## Wyniki sprzed integracji z Mistralem

Poniższe pomiary ekstrakcji z udziałem AI wykonano z modelem OpenAI. Na 60 publicznych sprawach reguły odczytały z tekstu m.in. 47/47 dostępnych numerów TED i 57/60 tytułów przelewów. Wszystkie odczytane numery i tytuły zgadzały się z etykietami. Po otrzymaniu nazw mocodawców reguły przypisały też 43 z 95 podpisów, wszystkie właściwym osobom i podmiotom.

W pomiarze obejmującym poprawki tytułów przelewów, podpisujących, sklejonych nazwisk pełnomocników i numerów TED mikro-F1 wzrosło z 96,23% do 97,65%, a liczba JSON-ów w pełni zgodnych z etykietą ze 125 do 149 na 180. Obie wersje dostały ten sam tekst źródłowy i te same zapisane wyniki modelu z przebiegu bez segmentacji. Reguły wyznaczyły wszystkie pola w 42 z 60 przelewów przed etapem AI. Trafienie wymaga tej samej ścieżki pola i niepustej wartości zgodnej z etykietą. Pomiar obejmuje publiczne sprawy użyte przy opracowaniu reguł.

W kolejnym teście samych odwołań sprawdzono także daty i kwalifikację pierwszego zarzutu. Przy tych samych zapisanych wynikach modelu mikro-F1 odwołań wzrosło z 96,23% do 97,09%. W pełni zgodnych było 38/60 dokumentów, wcześniej 32/60. Wszystkie 60 pól pełnomocnika z imieniem i nazwiskiem oraz wszystkie 60 pól TED odpowiadały etykietom, w tym 13 prawidłowych braków numeru TED.

W osobnym teście 60 publicznych pełnomocnictw porównano trzy wersje na zapisanych wynikach tego samego przebiegu AI. Mikro-F1 wyniosło kolejno 98,27%, 99,56% po pierwszej poprawce podpisów i 100,00% po poprawieniu dwóch dalszych list podpisujących oraz jednej nazwy mocodawcy. Liczba całych dokumentów zgodnych z etykietami UZP wzrosła z 51 do 57, a następnie do 60. Te same publiczne sprawy służyły do opracowania reguł.

Wariant z lokalną regułą zamawiających osiągnął mikro-F1 99,75% dla odwołań i 99,85% dla całego zestawu, wobec wcześniejszych 97,09% i 98,27%. Ten historyczny pomiar obejmował również poprawki rozpoznawania zaskarżonej czynności i jej daty. W pełni zgodnych było 176/180 dokumentów, wcześniej 158/180. Pomiar wykorzystał ponowny odczyt PDF-ów oraz te same zapisane wyniki AI. Kod, opis i data czynności zgadzały się z etykietami we wszystkich 60 odwołaniach.

Po przeniesieniu zasad rozpoznawania zamawiających do instrukcji JSONC wykonano 60 nowych wywołań modelu, po jednym dla każdego publicznego odwołania. Cała lista zamawiających była zgodna z etykietami w 60/60 dokumentów. Mikro-F1 sekcji wyniosło 100,00%, a całych odwołań 99,42% przy 53/60 w pełni zgodnych JSON-ach. Kontrolne zastosowanie poprzedniego parsera do tych samych odpowiedzi dało identyczne wyniki.

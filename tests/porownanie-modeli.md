# Porównanie modeli i diagnoza F1

## Skąd wziął się wynik 87,62%

W pierwszym przebiegu Ministral 8B trafił w 1235 niepustych pól. W 116 miejscach brakowało wartości, w 31 pojawiła się wartość nadmiarowa, a w 101 wartość różniła się od etykiety. Ta ostatnia kategoria daje zarazem fałszywe trafienie i brak. Łącznie było 132 FP i 217 FN, co daje 90,34% precyzji, 85,06% czułości i **87,62% mikro-F1**.

**Rachunki bankowe.** W 34 cyfrowych przelewach sprawdzono w PDF-ach oba rachunki. W 56 z 68 pól źródło zawierało `PL`, które pominięto w etykiecie. W 53 z tych 56 wynik był w całości zgodny z PDF-em, dwa pola były puste, a w jednym brakowało końcowych czterech cyfr. Spośród 53 trafień 48 rozstrzygnęły reguły lokalne, a 5 wymagało ekstrakcji przez model. Po przywróceniu kodu kraju w 56 sprawdzonych polach referencyjnych te same predykcje uzyskały **91,38% mikro-F1**. Reguła mentorów dotyczy obu stron przelewu i każdego kodu kraju widocznego w PDF-ie. [Ustalenia UZP](../USTALENIA-UZP.md#co-zapisywać-w-json-ie)

**Lista pełnomocników.** W 44 pełnomocnictwach etykiety zawierały 73 osoby. W pierwszym przebiegu aplikacja zapisała sześć rekordów. Lista była pusta w 31 z 34 cyfrowych dokumentów i we wszystkich dziesięciu skanach. W osobnej próbie zachowano odpowiedzi API dla wszystkich 44 pełnomocnictw. W 40 odpowiedziach model zwrócił listę pod kluczem `pełnomocnicy`, w trzech pod kanonicznym `pelnomocnicy`, a w jednej pojedynczy obiekt `pełnomocnik`. Dotychczasowy kod odzyskiwał wyłącznie pola odpowiadające dokładnej pisowni wzorca.

Po dwukrotnym przetworzeniu **tych samych 44 odpowiedzi** poprzedni kod zwrócił 5 rekordów, a poprawiony 72. Liczba pustych list spadła z 41 do zera. Cała lista, łącznie z kolejnością i numerami PESEL, była zgodna z etykietą w 33 dokumentach, wcześniej w trzech. Poprawiony wynik nadal zawiera w czterech dokumentach po jednej osobie za mało, w trzech po jednej za dużo, a w czterech innych ma właściwą długość i rozbieżność w treści lub kolejności. [Odzyskiwanie JSON-u](../odwolania/extraction.py) · [Wzorzec pełnomocnictwa](../oczekiwane-json/pelnomocnictwo.jsonc)

**Pozostałe błędy.** W skanie odwołania 0006 odczytano identyfikatory postępowania i TED, ale pseudonimizacja włączyła je do znaczników tytułu zamówienia. Oba pola zostały puste. W skanie 0007 OCR odczytał początek numeru TED `2026/S` jako `2026/85`. W tym samym dokumencie poprawny KRS był dostępny w mapie, a wynik zawierał zera. Poprawa obsługi list i prefiksów dotyczy tylko części błędów ekstrakcji.

## Jak poprawiono odczyt rachunków

W sprawie 05 końcowe cztery cyfry rachunku odbiorcy znajdowały się w kolejnym wierszu zdania. W sprawie 23 numery nadawcy i odbiorcy były zapisane osobno pod ich adresami. Reguły odczytują teraz numer w obu układach, sprawdzają jego strukturę oraz granice pola i zachowują prefiks źródłowy. Dla sprawy 16 ten sam odczyt zachowuje oba numery bez prefiksu. W całej partii zmieniło się osiem pól rozwiązywanych lokalnie w czterech potwierdzeniach. Dwa z nich reguły przetwarzają już w całości, co zmniejsza liczbę żądań z 107 do 105 na 150 PDF-ów. [Reguły przelewów](../oczekiwane-json/przelew.py) · [Testy dla numerów z prefiksem i bez niego](test_reguly_przelewu.py)

Na wszystkich 60 cyfrowych przelewach reguły lokalne odczytały poprawnie 112 ze 120 rachunków, wcześniej 98. Każdą z 14 nowych wartości potwierdzono niezależnym odczytem tekstu z oryginalnego PDF-u. W dziesięciu skanach liczba rachunków zgodnych z publiczną etykietą pozostała na poziomie 17/20. Dwa pola były puste, a w jednym OCR zmienił cyfrę.

## Metoda pomiaru

Partia obejmowała 102 cyfrowe dokumenty z 34 publicznych spraw, 30 skanów z etykietami, jeden dodatkowy skan ze znaną klasą oraz 17 negatywów. Do pomiaru pól weszły 132 dokumenty. Puste obiekty dla negatywów oraz rozpoznanie klasy dodatkowego skanu oceniano osobno. Jest to lokalny test na danych publicznych, częściowo wykorzystywanych do strojenia. [Dokładny dobór partii](raport-vm.md) · [Rewizja danych UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796)

Każdy model dostał ten sam lokalny odczyt PDF-u, te same znaczniki i wzorce. Dla każdego dokumentu porównano skróty treści żądań po wyłączeniu identyfikatora modelu. Etykiety odczytywał dopiero skrypt oceniający. Ścisłe mikro-F1 wymaga identycznej wartości pod tą samą ścieżką, z uwzględnieniem pozycji w liście. Wariant z korektą rachunków dodaje `PL` wyłącznie w 56 polach sprawdzonych niezależnie w PDF-ach. W sprawach 02, 16, 18, 22, 27 i 32 oba rachunki są zapisane bez kodu kraju. W pozostałych 28 cyfrowych przelewach tej partii oba mają prefiks `PL`. Obydwa wyniki F1 opisują te same predykcje. Metoda jury na zbiorze niejawnym może być inna.

Pierwsza seria na kodzie `d688449` dała następujące wyniki. Każdy model wykonał 107 żądań, wszystkie zakończyły się HTTP 200. Między niezależnymi wywołaniami tego samego modelu odpowiedź może się zmienić. Wpływ samej poprawki parsera sprawdzano z zachowanymi odpowiedziami w drugiej serii.

| Model ekstrakcji | Mikro-F1 z publicznymi etykietami | Mikro-F1 po korekcie 56 prefiksów |
| --- | ---: | ---: |
| Ministral 3B 2512 | 69,96% | 73,62% |
| Ministral 8B 2512 | 87,62% | 91,38% |
| Mistral Small 4 | 82,41% | 86,49% |

W każdym wariancie `anon-legal-pl` używał lokalnego modelu NER spaCy. Opcjonalny generatywny Bielik 11,169 mld wymaga dodatkowego uruchomienia. W ostatniej kolumnie przeliczono jego hipotetyczny udział jako drugiego LLM. Punkty odpowiadają progom z tabeli przekazanej przez zespół. Organizator wycofał tę tabelę z publicznego README i zapowiedział dalsze wytyczne. [Opcja Bielika w użytym wydaniu anon-legal-pl](https://github.com/Dymirt/anon-legal-pl/blob/ed24629fd3a4d81f114390bebffcbc22d31e632c/anonimizuj.py#L69-L77) · [Zmiana UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/commit/519b26c6be0120144c43529b29ec73d441b836b1)

| Model | Średnia w pomiarze F1 | Punkty wg tabeli | Średnia i punkty przy dodatkowym Bieliku |
| --- | ---: | ---: | ---: |
| Ministral 3B | 3,849 mld | 20 | 7,509 mld / 20 pkt |
| Ministral 8B | 8,918 mld | 18 | 10,043 mld / 18 pkt |
| Ministral 14B | 13,945 mld | 18 | 12,557 mld / 18 pkt |
| Mistral Small 4 | ok. 119 mld | 4 | ok. 65,084 mld / 8 pkt |

## Porównanie po naprawie list i odczytu rachunków

Wyniki drugiej serii dotyczą wersji `870c7d7`. Każdy wiersz obejmuje te same 132 publiczne dokumenty z etykietami. Każda konfiguracja zwróciła 150 plików JSON, poprawnie rozpoznała klasy i odrzuciła 17 negatywów. Dla jednego odwołania Ministral 3B nie otrzymał odpowiedzi z powodu błędu transportu. Pierwsza próba dała 67,79% F1 względem publicznych etykiet i 71,89% po korekcie prefiksów. W tabeli uwzględniono odpowiedź otrzymaną na identyczne żądanie w osobnym przebiegu dla tego jednego PDF-u.

| Model | Precyzja wg etykiet | Czułość wg etykiet | Mikro-F1 wg etykiet | Mikro-F1 po korekcie prefiksów |
| --- | ---: | ---: | ---: | ---: |
| Ministral 3B | 74,05% | 63,09% | 68,13% | 72,22% |
| Ministral 8B | 90,29% | 89,67% | **89,98%** | **93,85%** |
| Mistral Small 4 | 90,14% | 78,72% | 84,04% | 88,16% |

Przewaga Ministrala 8B nad Small 4 na publicznych etykietach wyniosła 5,94 punktu procentowego. Empiryczny przedział 95% wyniósł od 2,30 do 9,72 punktu (3500 losowań ze zwracaniem, dokumenty cyfrowe z jednej sprawy losowane razem). Na 26 dodatkowych cyfrowych pełnomocnictwach spoza głównej partii poprawka parsera zwiększyła liczbę dosłownie zgodnych list z 1 do 21. Mikro-F1 wszystkich pól pełnomocnictwa na tych samych 26 odpowiedziach wzrosło z 83,76% do 90,82%.

## Osobny wynik dla skanów

Sprawdzono wszystkie 30 PDF-ów i 30 etykiet w `dane/skany` względem oficjalnej gałęzi `main` z 22 listopada (rewizja `eadffbc`). Komplet obejmował po 10 skanów każdego typu. W porównaniu wykorzystano ten sam odczyt OCR dla każdego modelu. Tabela podaje ścisłe mikro-F1 dla wersji `870c7d7`. [Folder UZP ze skanami](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796/dane/skany)

| Model | Odwołania | Pełnomocnictwa | Przelewy | Wszystkie 30 skanów | Precyzja | Czułość |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ministral 3B | 57,79% | 67,12% | 83,50% | 64,99% | 72,98% | 58,58% |
| Ministral 8B | 83,33% | 87,18% | 79,59% | 83,72% | 86,01% | 81,55% |
| Mistral Small 4 | 85,02% | 94,27% | 91,59% | **88,66%** | 92,91% | 84,79% |

Każdy model zwrócił niepuste listy we wszystkich dziesięciu skanowanych pełnomocnictwach. Ministral 8B zwrócił 17 rekordów na 17 oczekiwanych, a w dziewięciu dokumentach cała lista zgadzała się z etykietą. Pełna zgodność obu rachunków wystąpiła w siedmiu z dziesięciu skanowanych przelewów dla Ministrala 8B, w ośmiu dla Ministrala 3B i w dziewięciu dla Small 4.

Wizualna kontrola dziesięciu skanowanych przelewów potwierdziła wszystkie dwadzieścia rachunków z etykiet. Dwa miały prefiks `PL`, a osiemnaście było zapisanych bez prefiksu. W skanie 0007 na trzynastej pozycji rachunku nadawcy widnieje 8. Podstawowy OCR odczytał ją jako 6. Korekty 56 publicznych etykiet rachunków dotyczą dokumentów cyfrowych.

## Szybkie porównanie modeli do 14 mld parametrów

W europejskim API zespołu dostępny jest `ministral-14b-2512`. Producent opublikował w wagach BF16 dokładnie **13 945 031 680 parametrów**. W tym teście był jedynym generatywnym modelem. Jego średnia to **13,945 mld**, co według tabeli przekazanej przez zespół odpowiada 18 punktom. Przy hipotetycznym włączeniu Bielika średnia wyniosłaby 12,557 mld, również 18 punktów. [Wagi Ministrala 14B](https://huggingface.co/api/models/mistralai/Ministral-3-14B-Instruct-2512-BF16) · [Status wytycznych UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026#sposób-punktacji-llm)

Do próby wybrano z góry sześć równomiernie rozłożonych spraw cyfrowych po trzy dokumenty i po sześć skanów z każdej klasy. Oba modele otrzymały te same nowe instrukcje z trzech plików JSONC i ten sam odczyt OCR. Na każdy model przypadło 30 udanych żądań oraz sześć dokumentów przetworzonych lokalnie. Sprawdzono zgodność skrótów wszystkich żądań. W tej podpróbie podlegało korekcie osiem pól z potwierdzonym prefiksem `PL`.

| Zestaw i sposób oceny | Ministral 8B | Ministral 14B | Różnica dla 14B |
| --- | ---: | ---: | ---: |
| 36 dokumentów, etykiety publiczne | **90,65%** | 90,37% | −0,28 p.p. |
| 36 dokumentów, prefiksy według PDF | **92,73%** | 92,51% | −0,21 p.p. |
| 18 cyfrowych, prefiksy według PDF | **98,27%** | 94,30% | −3,97 p.p. |
| 18 skanów | 86,58% | **90,61%** | +4,03 p.p. |

Po korekcie prefiksów 14B miał wyższą precyzję (94,79% wobec 92,25%) i niższą czułość (90,34% wobec 93,21%). Sparowany przedział bootstrap 95% dla różnicy całkowitego F1 wyniósł od −4,87 do +3,39 p.p. Mała próba nie rozstrzyga, który model będzie lepszy na zbiorze jury. W komendzie konkursowej pozostaje Ministral 8B.

Po zastosowaniu ostatecznej normalizacji imion w wydaniu `58f5a3a` do tych samych odpowiedzi zmieniło się po jednym polu każdego modelu. Na 36 dokumentach F1 z prefiksami z PDF-u wyniosło wtedy **92,99% dla 8B i 92,78% dla 14B** (różnica −0,21 p.p., przedział 95% od −4,85 do +3,40). Na 18 skanach odpowiednio **87,12% i 91,16%**. W obu przypadkach poprawiła się wielka litera imienia w skanie 0001. Dokumenty cyfrowe zachowały wynik.

## Wpływ nowych reguł przy tych samych odpowiedziach 8B

Nowe wskazówki dla modelu zapisano przy właściwych polach w trzech wzorcach JSONC. Uściślają, jak powiązać pełnomocnika z jego danymi, odróżnić numer sprawy od TED, wybrać datę faktycznej operacji oraz gdzie kończy się wielowierszowy tytuł przelewu. Lokalne reguły weryfikują jednoznaczne rubryki na oryginalnym tekście oraz odtwarzają dane po podstawieniu znaczników. [Odwołania](../oczekiwane-json/odwolanie.jsonc) · [Pełnomocnictwa](../oczekiwane-json/pelnomocnictwo.jsonc) · [Przelewy](../oczekiwane-json/przelew.jsonc)

Żeby zmierzyć sam wpływ zmian lokalnych z wersji `58f5a3a`, użyto identycznych odczytów OCR i identycznych wcześniej zapisanych wyników Ministrala 8B. Ponowne zastosowanie starej wersji zachowało wszystkie 150 JSON-ów. Nowa poprawiła 32 ze 132 oznaczonych dokumentów i zachowała wynik w pozostałych 100. Mikro-F1 z prefiksami według PDF wzrosło **z 93,85% do 96,93%**. Na wszystkich 30 skanach wzrosło **z 83,72% do 89,61%**. Ten pomiar izoluje reguły lokalne. Wpływ nowych instrukcji na sam model wymaga świeżych odpowiedzi API.

| Rozpoznany problem | Wynik w kontroli z identycznymi odpowiedziami |
| --- | --- |
| Zduplikowani lub pominięci pełnomocnicy, tytuł zawodowy dołączony do nazwiska, mała pierwsza litera imienia po OCR | Cała lista zgodna z etykietą w **44 z 44** dokumentów, wcześniej 33. W 26 osobno odłożonych sprawach 21 → 26 całkowicie zgodnych list. |
| Numer referencyjny i TED w rubryce zamówienia, dane lidera konsorcjum, skrócona nazwa kancelarii, data bez źródła w nagłówku | F1 odwołań wzrosło z 94,14% do 97,26%. |
| Rola rachunku, data operacji i tytuł w skanowanych tabelach | F1 skanowanych potwierdzeń wzrosło z 79,59% do 90,57%. |

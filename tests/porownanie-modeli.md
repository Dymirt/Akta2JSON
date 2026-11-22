# Porównanie modeli i diagnoza F1

## Skąd wziął się wynik 87,62%

W pierwszym przebiegu Ministral 8B trafił w 1235 niepustych pól. W 116 miejscach brakowało wartości, w 31 pojawiła się wartość nadmiarowa, a w 101 wartość różniła się od etykiety. Ta ostatnia kategoria daje zarazem fałszywe trafienie i brak. Łącznie było 132 FP i 217 FN, co daje 90,34% precyzji, 85,06% czułości i **87,62% mikro-F1**.

**Rachunki bankowe.** W 34 cyfrowych przelewach sprawdzono w PDF-ach oba rachunki. W 56 z 68 pól źródło zawierało `PL`, które pominięto w etykiecie. W 53 z tych 56 wynik był w całości zgodny z PDF-em, dwa pola były puste, a w jednym brakowało końcowych czterech cyfr. Spośród 53 trafień 48 rozstrzygnęły reguły lokalne, a 5 wymagało ekstrakcji przez model. Po przywróceniu kodu kraju w 56 sprawdzonych polach referencyjnych te same predykcje uzyskały **91,38% mikro-F1**. Reguła mentorów dotyczy obu stron przelewu i każdego kodu kraju widocznego w PDF-ie. [Ustalenia UZP](../USTALENIA-UZP.md#co-zapisywać-w-json-ie)

**Lista pełnomocników.** W 44 pełnomocnictwach etykiety zawierały 73 osoby. W pierwszym przebiegu aplikacja zapisała sześć rekordów. Lista była pusta w 31 z 34 cyfrowych dokumentów i we wszystkich dziesięciu skanach. W osobnej próbie zachowano odpowiedzi API dla wszystkich 44 pełnomocnictw. W 40 odpowiedziach model zwrócił listę pod kluczem `pełnomocnicy`, w trzech pod kanonicznym `pelnomocnicy`, a w jednej pojedynczy obiekt `pełnomocnik`. Dotychczasowy kod odzyskiwał wyłącznie pola odpowiadające dokładnej pisowni wzorca.

Po dwukrotnym przetworzeniu **tych samych 44 odpowiedzi** poprzedni kod zwrócił 5 rekordów, a poprawiony 72. Liczba pustych list spadła z 41 do zera. Cała lista, łącznie z kolejnością i numerami PESEL, była zgodna z etykietą w 33 dokumentach, wcześniej w trzech. Poprawiony wynik nadal zawiera w czterech dokumentach po jednej osobie za mało, w trzech po jednej za dużo, a w czterech innych ma właściwą długość i rozbieżność w treści lub kolejności. [Odzyskiwanie JSON-u](../odwolania/extraction.py) · [Wzorzec pełnomocnictwa](../oczekiwane-json/pelnomocnictwo.jsonc)

**Pozostałe błędy.** W skanie odwołania 0006 odczytano identyfikatory postępowania i TED, ale pseudonimizacja włączyła je do znaczników tytułu zamówienia. Oba pola zostały puste. W skanie 0007 OCR odczytał początek numeru TED `2026/S` jako `2026/85`. W tym samym dokumencie poprawny KRS był dostępny w mapie, a wynik zawierał zera. Poprawa obsługi list i prefiksów dotyczy tylko części błędów ekstrakcji.

## Jak poprawiono odczyt rachunków

W sprawie 05 końcowe cztery cyfry rachunku odbiorcy znajdowały się w kolejnym wierszu zdania. W sprawie 23 numery nadawcy i odbiorcy były zapisane osobno pod ich adresami. Reguły odczytują teraz numer w obu układach, sprawdzają jego strukturę oraz granice pola i zachowują prefiks źródłowy. Dla sprawy 16 ten sam odczyt zachowuje oba numery bez prefiksu. W całej partii zmieniło się osiem pól rozwiązywanych lokalnie w czterech potwierdzeniach. Dwa z nich reguły przetwarzają już w całości, co zmniejsza liczbę żądań z 107 do 105 na 150 PDF-ów. [Reguły przelewów](../oczekiwane-json/przelew.py) · [Testy dla numerów z prefiksem i bez niego](test_reguly_przelewu.py)

## Metoda pomiaru

Partia obejmowała 102 cyfrowe dokumenty z 34 publicznych spraw, 30 skanów z etykietami, jeden dodatkowy skan ze znaną klasą oraz 17 negatywów. Do pomiaru pól weszły 132 dokumenty. Puste obiekty dla negatywów oraz rozpoznanie klasy dodatkowego skanu oceniano osobno. Jest to lokalny test na danych publicznych, częściowo wykorzystywanych do strojenia. [Dokładny dobór partii](raport-vm.md) · [Rewizja danych UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796)

Każdy model dostał ten sam lokalny odczyt PDF-u, te same znaczniki i wzorce. Dla każdego dokumentu porównano skróty treści żądań po wyłączeniu identyfikatora modelu. Etykiety odczytywał dopiero skrypt oceniający. Ścisłe mikro-F1 wymaga identycznej wartości pod tą samą ścieżką, z uwzględnieniem pozycji w liście. Wariant z korektą rachunków dodaje `PL` wyłącznie w 56 polach sprawdzonych niezależnie w PDF-ach. W sprawach 02, 16, 18, 22, 27 i 32 oba rachunki są zapisane bez kodu kraju. W pozostałych 28 cyfrowych przelewach tej partii oba mają prefiks `PL`. Obydwa wyniki F1 opisują te same predykcje. Metoda jury na zbiorze niejawnym może być inna.

Pierwsza seria na kodzie `d688449` dała następujące wyniki. Każdy model wykonał 107 żądań, wszystkie zakończyły się HTTP 200. Między niezależnymi wywołaniami tego samego modelu odpowiedź może się zmienić. Wpływ samej poprawki parsera sprawdzano z zachowanymi odpowiedziami w drugiej serii.

| Model ekstrakcji | Mikro-F1 z publicznymi etykietami | Mikro-F1 po korekcie 56 prefiksów |
| --- | ---: | ---: |
| Ministral 3B 2512 | 69,96% | 73,62% |
| Ministral 8B 2512 | 87,62% | 91,38% |
| Mistral Small 4 | 82,41% | 86,49% |

W każdym z tych wariantów `anon-legal-pl` używał lokalnego modelu NER spaCy. Opcjonalny generatywny Bielik wymaga dodatkowego uruchomienia. Średnie rozmiary i przeliczenie na punkty dla każdej konfiguracji opisuje [tabela modeli i punktacji](../README.md#modele-używane-przy-ekstrakcji-i-pseudonimizacji).

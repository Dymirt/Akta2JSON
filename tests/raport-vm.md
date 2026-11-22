# Próba konkursowa na 150 PDF-ach

## VM UZP, 22 listopada 2026 r.

Na konkursowej VM komenda z `RUN.md` zakończyła się kodem **0 po 13 min 37 s**. Limit organizatora wynosi **60 minut**. Na Ubuntu 24.04.5 LTS z 2 vCPU uruchomiono lokalny obraz AMD64, dwa procesy i regionalny model `mistral-small-2603`. Do pustych katalogów testowych trafiła partia opisana poniżej. Odczytano 410 stron z warstwą tekstową i 86 przez OCR. [Badany commit](https://github.com/Dymirt/Akta2JSON/commit/bc4c2a0300c0f62e06a23d327f11787b83b2b150) · [Komenda oceny](../RUN.md) · [Aktualny limit](../USTALENIA-UZP.md#limit-czasu-na-przetworzenie-partii)

Powstało 150 plików JSON pod oczekiwanymi ścieżkami, wszystkie w trybie `0600`. Poprawnie rozpoznano 45 odwołań, 44 pełnomocnictwa i 44 przelewy. Każdy z 17 negatywów zawierał dokładnie dwa bajty `{}`. Program zgłosił zero błędów przetwarzania.

| Pola porównane z etykietami | Dokumenty | Cały JSON zgodny | Precyzja | Czułość | Mikro-F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dokumenty cyfrowe | 102 | 43 | 90,01% | 89,06% | 89,53% |
| Skany z etykietami | 30 | 11 | 89,29% | 80,91% | 84,89% |
| **Łącznie** | **132** | **54** | **89,87%** | **87,33%** | **88,58%** |

Ścisłe porównanie pól uwzględnia ścieżkę, pozycję na liście i wartość. Wynik obejmuje 1268 trafień, 143 wartości fałszywie dodatnie i 184 fałszywie ujemne. Wykorzystano publiczne sprawy używane także podczas strojenia. Dla rachunków z prefiksem obecnym w PDF-ie porównanie z etykietą pomijającą prefiks liczy rozbieżność.

W trzech skanach odwołań (`0002`, `0004`, `0005`) cztery NIP-y stron miały prawidłowe cyfry i myślniki z PDF-u. Dodano dwie reguły normalizacji w JSONC i ponownie wykonano pełną ekstrakcję tych trzech PDF-ów na VM. Wszystkie cztery NIP-y zgodziły się z etykietami. W połączonym zestawie 147 poprzednich i 3 nowych wyników kontrola formatu przeszła dla wszystkich 150 plików. Na 132 dokumentach z etykietami uzyskano **90,08% precyzji, 87,53% czułości i 88,79% mikro-F1** (1271 TP, 140 FP i 181 FN). Czas 13 min 37 s dotyczy pierwszego pełnego przebiegu.

W osobnej próbie bez sieci przetworzono wszystkie cztery dokumenty ze sprawy 04 i skan przelewu 0001. Dla każdego PDF-u mapa przywróciła pełny oryginalny tekst odczytany z PDF-a. W 84 z 253 podstawień wykorzystano wcześniej użyty znacznik, a każdy z dziesięciu plików tekstu i mapy miał uprawnienia `0600`.

## Wcześniejsza próba na lokalnym ARM64

22 listopada 2026 r. komenda z `RUN.md` przetworzyła **150 PDF-ów w 10 min 58 s**. Zakończyła się kodem `0`. Pomiar obejmuje uruchomienie i zakończenie kontenera, odczyt 410 stron tekstowych, OCR 86 stron oraz ekstrakcję przez regionalne API Mistral. [RUN.md](../RUN.md) · [Materiały UZP w badanej rewizji](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796)

Pomiar wykonano lokalnie w Docker Desktop na Linux ARM64, z limitem 2 vCPU dla kontenera. Maszyna Dockera miała 7,65 GiB RAM. Zbudowano również obraz `linux/amd64` i w emulacji sprawdzono na nim skan, przelew z warstwą tekstową i negatyw. Pomiar 150 plików dotyczy ARM64.

### Wersja objęta pomiarem

Pełny przebieg ukończono przed równoległą aktualizacją formatu negatywów i rachunków według odpowiedzi mentorów. Poniższe czasy i metryki dotyczą wersji z chwili startu próby. Bieżący kontrakt wymaga dla negatywu dokładnie dwóch bajtów `{}` i zachowania widocznego kodu kraju rachunku. Publiczne etykiety cyfrowe pomijają część prefiksów. [Ustalenia mentorów](../USTALENIA-UZP.md)

Po aktualizacji ponownie przetworzono wszystkie 17 negatywów w kontenerze bez sieci. Każdy wynik zawierał dokładnie `{}` i miał uprawnienia `0600`. W dwóch skanowanych potwierdzeniach z prefiksem `PL` program zachował go przy rachunku nadawcy i pozostawił rachunek odbiorcy bez prefiksu, zgodnie z PDF-em. Na 60 cyfrowych przelewach wszystkie 98 ze 120 rachunków odczytanych przez reguły odpowiadało zapisowi źródłowemu po usunięciu odstępów. Pozostałe 22 rachunki wymagają ekstrakcji przez model. Wariant `linux/amd64` przeszedł próbę z nowym formatem negatywu, skanem i tekstowym przelewem. Ówczesny zestaw 129 testów jednostkowych i integracyjnych przeszedł w Dockerze.

### Klasyfikacja i ekstrakcja

Początkowo pusty katalog wynikowy zawierał po zakończeniu dokładnie 150 plików. Wszystkie miały właściwą ścieżkę względną i uprawnienia `0600`. Program poprawnie sklasyfikował 133 dokumenty trzech obsługiwanych typów. Dla wszystkich 17 negatywów utworzył pliki o długości 0 bajtów.

| Pola porównane z etykietami | Dokumenty | Cały JSON zgodny | Precyzja | Czułość | Mikro-F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dokumenty cyfrowe | 102 | 68 | 96,42% | 91,78% | 94,04% |
| Skany odwołań | 10 | 0 | 83,85% | 76,27% | 79,88% |
| Skany pełnomocnictw | 10 | 6 | 89,61% | 88,46% | 89,03% |
| Skany przelewów | 10 | 3 | 86,79% | 85,19% | 85,98% |
| **Wszystkie skany z etykietami** | **30** | **9** | **85,91%** | **80,91%** | **83,33%** |
| **Łącznie** | **132** | **77** | **94,20%** | **89,46%** | **91,77%** |

Trafienie wymagało tej samej niepustej wartości pod tą samą ścieżką JSON, z uwzględnieniem indeksu listy. Tekst porównano znak w znak, liczby według wartości liczbowej. Błędna wartość daje jeden wynik fałszywie dodatni i jeden fałszywie ujemny. Łącznie odnotowano 1299 TP, 80 FP i 153 FN. Mikro-F1 wynosi `2 × TP / (2 × TP + FP + FN)`. W opisie oceny mentorzy dopuszczają dopasowanie rekordów list po treści i podobieństwo długich pól. Podane tu wyniki liczą zgodność ścisłą. Skan z szablonu organizatora ma znaną klasę, bez etykiety pól. Negatywy oceniono osobno.

Najwięcej rozbieżności w skanach dotyczyło odwołań, m.in. NIP-ów stron i nazw kancelarii. W dwóch przelewach etykieta UZP zachowuje prefiks `PL` przy rachunku, a wersja z próby zwracała same cyfry.

### Dobór danych i warunki próby

Do pustego drzewa wejściowego skopiowano tylko publiczne PDF-y. Użyto wszystkich 30 numerowanych skanów, 17 negatywów, skanu odwołania z szablonu aplikacji oraz trzech typów dokumentów ze spraw 01, 02, 04, 05, 06, 07, 08, 14, 16, 18, 19, 20, 22, 23, 25, 27, 28, 29, 31, 32, 34, 35, 36, 37, 40, 43, 44, 46, 47, 50, 55, 56, 57 i 60. Etykiety posłużyły do porównania po ekstrakcji. Publiczne przykłady wykorzystano również do strojenia reguł, więc pomiar opisuje jakość na tym zestawie.

Pierwsza próba na tych samych dokumentach zakończyła się 16 błędami HTTP 429. W próbie końcowej dwa procesy współdzieliły limit 15 żądań na minutę i uwzględniały podany przez usługę koszt tokenów. Użyto modelu `mistral-small-2603`. API obsłużyło tę partię bez błędów.

Osobny test klasyfikacji na całym opublikowanym zestawie poprawnie rozpoznał 211 dokumentów pozytywnych i odrzucił wszystkie 17 negatywów. [Skrypt pomiarowy](sprawdz_reguly.py)

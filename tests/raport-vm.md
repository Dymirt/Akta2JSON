# Próba konkursowa na 150 PDF-ach

22 listopada 2026 r. komenda z `RUN.md` przetworzyła **150 PDF-ów w 10 min 58 s**. Zakończyła się kodem `0`. Limit UZP wynosi 45 minut. Pomiar obejmuje uruchomienie i zakończenie kontenera, odczyt 410 stron tekstowych, OCR 86 stron oraz ekstrakcję przez regionalne API Mistral. [RUN.md](../RUN.md) · [Materiały UZP w badanej rewizji](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796)

Pomiar wykonano lokalnie w Docker Desktop na Linux ARM64, z limitem 2 vCPU dla kontenera. Maszyna Dockera miała 7,65 GiB RAM. Zbudowano również obraz `linux/amd64` i w emulacji sprawdzono na nim skan, przelew z warstwą tekstową i negatyw. Pomiar 150 plików dotyczy ARM64.

## Wersja objęta pomiarem

Pełny przebieg ukończono przed równoległą aktualizacją formatu negatywów i rachunków według odpowiedzi mentorów. Poniższe czasy i metryki dotyczą wersji z chwili startu próby. Bieżący kontrakt wymaga dla negatywu dokładnie dwóch bajtów `{}` i zachowania widocznego kodu kraju rachunku. Publiczne etykiety cyfrowe pomijają część prefiksów. [Ustalenia mentorów](../USTALENIA-UZP.md)

Po aktualizacji ponownie przetworzono wszystkie 17 negatywów w kontenerze bez sieci. Każdy wynik zawierał dokładnie `{}` i miał uprawnienia `0600`. W dwóch skanowanych potwierdzeniach z prefiksem `PL` program zachował go przy rachunku nadawcy i pozostawił rachunek odbiorcy bez prefiksu, zgodnie z PDF-em. Na 60 cyfrowych przelewach wszystkie 98 ze 120 rachunków odczytanych przez reguły odpowiadało zapisowi źródłowemu po usunięciu odstępów. Pozostałe 22 rachunki wymagają ekstrakcji przez model. Wariant `linux/amd64` przeszedł próbę z nowym formatem negatywu, skanem i tekstowym przelewem. Bieżący zestaw 129 testów jednostkowych i integracyjnych przeszedł w Dockerze.

## Klasyfikacja i ekstrakcja

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

## Dobór danych i warunki próby

Do pustego drzewa wejściowego skopiowano tylko publiczne PDF-y. Użyto wszystkich 30 numerowanych skanów, 17 negatywów, skanu odwołania z szablonu aplikacji oraz trzech typów dokumentów ze spraw 01, 02, 04, 05, 06, 07, 08, 14, 16, 18, 19, 20, 22, 23, 25, 27, 28, 29, 31, 32, 34, 35, 36, 37, 40, 43, 44, 46, 47, 50, 55, 56, 57 i 60. Etykiety posłużyły do porównania po ekstrakcji. Publiczne przykłady wykorzystano również do strojenia reguł, więc pomiar opisuje jakość na tym zestawie.

Pierwsza próba na tych samych dokumentach zakończyła się 16 błędami HTTP 429. W próbie końcowej dwa procesy współdzieliły limit 15 żądań na minutę i uwzględniały podany przez usługę koszt tokenów. Użyto modelu `mistral-small-2603`. API obsłużyło tę partię bez błędów.

Osobny test klasyfikacji na całym opublikowanym zestawie poprawnie rozpoznał 211 dokumentów pozytywnych i odrzucił wszystkie 17 negatywów. [Skrypt pomiarowy](sprawdz_reguly.py)

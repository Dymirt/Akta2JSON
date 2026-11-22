# Odwołania2JSON

Odwołania2JSON zamienia odwołania, pełnomocnictwa i potwierdzenia przelewów z akt Krajowej Izby Odwoławczej (KIO) w dane do analizy. Odczytuje zarówno PDF-y z tekstem, jak i skany. Dla każdego rozpoznanego pisma tworzy osobny plik JSON według wzorca Urzędu Zamówień Publicznych (UZP). W tych danych można wyszukać sprawy według zaskarżonej czynności, sprawdzić, kto reprezentował wykonawcę, lub odczytać kwotę wpłaty.

[Uruchom na maszynie konkursowej](RUN.md) · [Zobacz wyniki próby na 150 PDF-ach](#wyniki-na-maszynie-uzp)

## Dwie daty w jednym odwołaniu

W publicznym przykładzie UZP zamawiający unieważnił postępowanie `ZP.447.2026` 11 sierpnia. Wykonawca wniósł odwołanie 24 sierpnia. W tym fragmencie wyniku każda data ma własne pole, a kod `9` pozwala znaleźć inne odwołania dotyczące unieważnienia postępowania. [Odwołanie w PDF](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/dane/przyklad_04/odwolanie.pdf) · [Wzorcowy wynik UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/eadffbce531eeac876d0f7e62c1cc6e857b05796/dane/przyklad_04/odwolanie.json)

```json
{
  "OdwolanieKIO": {
    "data": "2026-08-24",
    "czynnosc_dzien": "2026-08-11",
    "czynnosc_powod_id": 9,
    "czynnosc_opis": "Decyzja o unieważnieniu postępowania",
    "miejscowosc": "Katowice"
  }
}
```

## Wyniki na maszynie UZP

**150 publicznych PDF-ów w 13 min 11 s** przy limicie 60 minut. W próbie z Ministralem 8B na VM UZP (wersja `870c7d7`, 2 vCPU, bez GPU) aplikacja zakończyła pracę z kodem 0. Rozpoznała 133 pisma obsługiwanych klas, a dla pozostałych 17 dokumentów zwróciła pusty obiekt `{}`.

Na 132 dokumentach z etykietami ścisłe **mikro-F1 pól wyniosło 89,92%** (precyzja 89,83%, czułość 90,01%). Po korekcie etykiet prefiksów według PDF-ów mikro-F1 wyniosło **93,77%**. Na 30 skanach wynik wyniósł **85,29%**. Trafienie wymagało zgodności wartości i jej miejsca w JSON-ie. Część publicznych spraw służyła również do strojenia reguł. [Porównanie modeli i pomiar wpływu późniejszych reguł](tests/porownanie-modeli.md) · [Wcześniejsza próba z Mistral Small 4](tests/raport-vm.md)

Mentorzy potwierdzili, że oba rachunki należy przepisać z PDF-u. JSON zachowuje `PL` lub inny widoczny prefiks, a numer bez prefiksu pozostaje bez prefiksu. W pierwszym przebiegu Ministrala 8B **w 53 polach model poprawnie zachował prefiks `PL` widoczny w PDF-ie, a publiczna etykieta go pomijała**. [Porównanie F1 z publicznymi i sprawdzonymi etykietami](tests/porownanie-modeli.md)

## Dlaczego na VM wybraliśmy Ministral 8B

**Na 36 PDF-ach Ministral 8B uzyskał 92,99% mikro-F1, a Ministral 14B uzyskał 92,78%.** Do odpowiedzi obu modeli zastosowano końcowe reguły normalizacji, a prefiksy rachunków oceniono według dokumentów. Na 18 skanach lepszy wynik osiągnął 14B (91,16% wobec 87,12% dla 8B). Na 18 dokumentach cyfrowych wyższy wynik miał 8B (98,27% wobec 94,30% dla 14B).

Różnica ogólna mieści się w niepewności pomiaru. Na VM wdrożyliśmy Ministral 8B. [Metoda porównania i przedział ufności](tests/porownanie-modeli.md#szybkie-porównanie-modeli-do-14-mld-parametrów)

## Jak aplikacja korzysta z modelu

Aplikacja lokalnie rozpoznaje typ pisma, zastępuje wykryte dane znacznikami i odczytuje jednoznaczne pola za pomocą reguł. Gdy reguły ustalą wszystkie pola, plik JSON powstaje bez wywołania API. Jeśli zostały pola do uzupełnienia, aplikacja wysyła do API Mistrala jedno żądanie z pełnym tekstem po pseudonimizacji, wzorcem i listą już ustalonych pól. Oryginalne wartości przywraca z mapy, która pozostaje na maszynie użytkownika. Komenda konkursowa korzysta z modelu Ministral 8B. [Konfiguracja modelu](RUN.md#usługa-zewnętrzna) · [Porównanie modeli](tests/porownanie-modeli.md)

Na potrzeby projektu rozszerzyliśmy bibliotekę `anon-legal-pl` m.in. o maskowanie numerów postępowań oraz ogłoszeń BZP i TED. Poprawki wraz z testami zgłosiliśmy autorowi biblioteki. [Pull request w projekcie źródłowym](https://github.com/apiotrowski-afk/anon-legal-pl/pull/2)

## Dodawanie typu dokumentu

Do obsługi kolejnego rodzaju pisma, np. protokołu odbioru, wystarczy jeden plik JSONC. Określa on nagłówek rozpoznawany w PDF-ie, pola wyniku i ich znaczenie. Aplikacja odczytuje wzorzec przy kolejnym uruchomieniu, bez przebudowy obrazu Dockera. [Przykład protokołu odbioru](DOKUMENTACJA.md#dodawanie-typu-dokumentu) · [Trzy wzorce konkursowe](oczekiwane-json/)

[Dokumentacja techniczna](DOKUMENTACJA.md) · [Wdrożenie na VM](deploy/README.md) · [Ustalenia z mentorami UZP](USTALENIA-UZP.md) · [Repozytorium projektu](https://github.com/Dymirt/Akta2JSON)

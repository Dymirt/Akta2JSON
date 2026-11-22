"""Reguły dla potwierdzeń przelewów z jednoznacznie opisanymi polami."""

import re
from datetime import date
from decimal import Decimal

from odwolania.bank_accounts import FOREIGN_IBAN
from odwolania.templates import FORMATTERS, QUOTE_PAIRS, normalize_spaces


ETYKIETY = {
    "data_operacji": r"data (?:operacji|realizacji|transakcji|wykonania)",
    "kwota": r"kwota(?: operacji| przelewu)?|wartość",
    "waluta": r"waluta",
    "na_rachunek": r"rachunek (?:odbiorcy|beneficjenta|kontrahenta|uznawany)|na rachunek",
    "z_rachunku": r"rachunek (?:nadawcy|zleceniodawcy|obciążany)|z rachunku",
    "numer_transakcji": r"numer referencyjny(?: (?:transakcji|operacji))?|(?:numer transakcji|nr ref\.)(?: operacji)?|identyfikator operacji",
    "tytul": r"tytuł(?: przelewu)?|tytułem|opis",
}
POLA = {
    pole: re.compile(rf"(?:{etykieta})(?:(?:\s*:\s*|\s*\.{{2,}}\s*|\s+)(.*))?", re.IGNORECASE)
    for pole, etykieta in ETYKIETY.items()
}
SEPARATOR = r"\s*:\s*|\s*\.{2,}\s*"
CUDZYSLOWY = re.escape("".join(QUOTE_PAIRS))
POLA["tytul"] = re.compile(
    rf"(?:{ETYKIETY['tytul']})(?:(?:{SEPARATOR}|\s+(?=[{CUDZYSLOWY}]))(.*))?", re.IGNORECASE
)
ETYKIETA_FORMULARZA = re.compile(
    rf"(?:{'|'.join(ETYKIETY.values())}|status|kanał|typ operacji)(?:(?:{SEPARATOR}).*)?", re.IGNORECASE
)
KWOTA = re.compile(
    r"(?:(PLN|zł) )?[−-]?([0-9]+(?: [0-9]{3})*(?:[,.][0-9]{2})?)(?: (PLN|zł))?",
    re.IGNORECASE,
)
NAGLOWEK_TABELI = re.compile(r"Kwota Data transakcji(?: (Numer referencyjny transakcji))?", re.I)
KWOTA_Z_WALUTA = r"[−-]?[0-9]+(?: [0-9]{3})*[.,][0-9]{2} (?:PLN|zł)"
WIERSZ_TRANSAKCJI = re.compile(
    rf"({KWOTA_Z_WALUTA})\s+(?:[^\d ]\s+)?(\d{{2}}\.\d{{2}}\.\d{{4}})(?:\s+[*|]?\s*(\S+))?", re.I
)
RACHUNEK_KRAJOWY = re.compile(r"(?ai:(?:PL)?[0-9]{24}(?:[0-9]{2})?)")
RACHUNEK_W_TABELI = re.compile(
    FOREIGN_IBAN.pattern + r"|(?<!\w)(?:(?ai:PL) ?|(?<![0-9] )(?<!\b[A-Za-z]{2} ))"
    r"[0-9]{2}(?: ?[0-9]{4}){6}(?!\w| [0-9])"
)
SEKCJA_BANKOWA = re.compile(r"dane (nadawcy|odbiorcy|zleceniodawcy|kontrahenta|zlecenia)", re.I)
STRONY_PRZELEWU = {
    "nadawca": "Z rachunku", "dane nadawcy": "Z rachunku",
    "odbiorca": "Na rachunek", "dane odbiorcy": "Na rachunek",
}
NUMER_W_ZDANIU = r" nr ((?:[A-Z]{2} *)?[0-9]{2}[A-Z0-9 ]{0,65}(?:\n[A-Z0-9 ]{1,65})?),[ \n]*"
RACHUNKI_W_ZDANIU = {
    "z_rachunku": re.compile(
        r"^Bank potwierdza, że w dniu [^\n\f;:]{1,45} z rachunku" + NUMER_W_ZDANIU + r"prowadzonego dla\b", re.I | re.M
    ),
    "na_rachunek": re.compile(
        r"\bwykonano przelew(?: krajowy)? w kwocie [0-9][0-9., ]*(?:[a-z]{3}|zł)? na rachunek"
        + NUMER_W_ZDANIU + r"prowadzony dla\b", re.I
    ),
}
STOPKA_BANKU = re.compile(r"Dokument jest wydrukiem kompu[ti]erowym\b", re.I)
SZCZEGOLY_OBCIAZENIA = re.compile(r"(?:. \* )?Przelew z rachunku:? Szczegóły transakcji", re.I)
# Przykłady ciągłości wiersza: numer sprawy, faktury lub transakcji.
ODSYLACZ = re.compile(r"\b(?:[^\W\d_]+[./_-]?[0-9]|[0-9]+[/_-][0-9]+)")


def _wiersze(tekst):
    wiersze = []
    for numer, strona in enumerate(tekst.split("\f")):
        if numer:
            wiersze.append("\f")
        strona = [normalize_spaces(wiersz) for wiersz in strona.splitlines() if wiersz.strip()]
        wiersze.extend(_wiersze_tabeli(strona))
    return wiersze


def _rachunki_pionowe(strona):
    """Nazwa, adres z kodem pocztowym i samodzielny rachunek pod nagłówkiem strony."""
    naglowki = [(i, STRONY_PRZELEWU[w.casefold()]) for i, w in enumerate(strona) if w.casefold() in STRONY_PRZELEWU]
    if len(naglowki) != 2 or naglowki[0][1] == naglowki[1][1]:
        return
    for i, rola in naglowki:
        if i + 4 >= len(strona):
            continue
        nazwa, adres, rachunek, granica = strona[i + 1:i + 5]
        if granica.casefold() not in STRONY_PRZELEWU and not ETYKIETA_FORMULARZA.fullmatch(granica):
            continue
        if not re.search(r"\b[0-9]{2}-[0-9]{3}\s+[^\W\d_]", adres) or not RACHUNEK_W_TABELI.fullmatch(rachunek):
            continue
        if (re.search(r"[^\W\d_]", nazwa) and ":" not in nazwa and not ETYKIETA_FORMULARZA.fullmatch(nazwa)
                and not RACHUNEK_W_TABELI.search(nazwa) and not RACHUNEK_W_TABELI.search(adres)):
            yield i + 3, rola


def _szczegoly_obciazenia(strona):
    """Powiąż komórki formularza z kolumnami tylko przy jednym przelewie wychodzącym."""
    naglowki = [i for i, w in enumerate(strona) if SZCZEGOLY_OBCIAZENIA.fullmatch(w)]
    odbiorcy = [i for i, w in enumerate(strona) if w.casefold() == "rachunek odbiorcy:"]
    if len(naglowki) != 1 or len(odbiorcy) != 1:
        return strona
    i, j = naglowki[0] + 1, odbiorcy[0]
    if i >= j:
        return strona
    wynik = strona.copy()
    numer = re.fullmatch(r"(?:\w )?Numer rachunku (.+)", strona[i], re.I)
    if numer and RACHUNEK_W_TABELI.fullmatch(numer[1]):
        wynik[i] = "Z rachunku: " + numer[1]
        if strona[j - 1].casefold() == "opis":
            wynik[j - 1] = ""  # Nagłówek sekcji obejmującej m.in. tytuł i rachunek odbiorcy.
        for k in range(j + 1, len(strona) - 1):
            if (strona[k].casefold() == "typ transakcji przelew z rachunku" and
                    re.fullmatch(rf"Kwota ({KWOTA_Z_WALUTA})", strona[k + 1], re.I)):
                poczatki = [n for n in range(j + 1, k) if strona[n].casefold() == "tytuł:"]
                if len(poczatki) == 1:
                    n = poczatki[0]
                    if n + 1 < k and all(not re.search(r":|\.{2,}", w) and
                                         not ETYKIETA_FORMULARZA.fullmatch(w) for w in strona[n + 1:k]):
                        wynik[n:k] = ["Tytuł: " + " ".join(strona[n + 1:k])] + [""] * (k - n - 1)
    elif (i + 7 < j and [w.casefold() for w in strona[i:i + 5]] ==
          ["numer rachunku", "data waluty", "data operacji", "opis", "typ transakcji"]
          and RACHUNEK_W_TABELI.fullmatch(strona[j - 3])
          and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", w) for w in strona[j - 2:j])
          and not any(RACHUNEK_W_TABELI.search(w) or re.search(r"\d{4}-\d{2}-\d{2}", w)
                      for w in strona[i + 5:j - 3])):
        wynik[i + 2:i + 4] = ["", ""]
        wynik[j - 3] = "Z rachunku: " + strona[j - 3]
        wynik[j - 1] = "Data operacji: " + strona[j - 1]
        for k in range(j + 1, len(strona) - 1):
            if strona[k].casefold() == "przelew z rachunku" and re.fullmatch(KWOTA_Z_WALUTA, strona[k + 1], re.I):
                wynik[k + 1] = "Kwota: " + strona[k + 1]
    return wynik


def _data_wykonanego_zlecenia(strona):
    """Datę zleconą potwierdzają wykonanie operacji i ten sam dzień na podpisanym potwierdzeniu."""
    tekst = "\n".join(strona)
    if not re.search(r"(?im)^Szczegóły zlecenia(?: \w)?\nTyp zlecenia[: ]+Przelew krajowy\n"
                     r"(?:Status[ .:]*|[_. ]*[A-Z]{1,2} )wykonane\nDane zleceniodawcy$", tekst):
        return
    if sum(w.casefold() == "dane zlecenia" for w in strona) != 1:
        return
    m = re.search(r"(?im)^Data: (\d{4})\.(\d{2})\.(\d{2}) \d{2}:\d{2}:\d{2} (?:CEST|CET)\b", tekst)
    if not m:
        return
    for i, w in enumerate(strona):
        zlecona = re.fullmatch(r"Z[ltł]econa data wykonania (\d{2})[. ](\d{2})[. ](\d{4})(?: [.* ]+)?", w, re.I)
        if zlecona and zlecona.groups()[::-1] == m.groups():
            yield i, "Data wykonania: " + "-".join(m.groups())


def _wiersze_tabeli(strona):
    """Rozdziel nagłówki i komórki, które OCR odczytał poziomo w jednym wierszu."""
    strona = [w for w in _szczegoly_obciazenia(strona) if w]
    daty = dict(_data_wykonanego_zlecenia(strona))
    kolumny_wyciagu = any(w.casefold() == "data opis kwota" for w in strona)
    # W dwukolumnowym formularzu OCR potrafi odczytać najpierw etykiety, potem rachunki z nazwami stron.
    tekst_strony = "\n".join(strona)
    kolejnosc_stron = re.search(r"(?im)^dane[ .]*\nnadawcy\ndane[ .]*\nodbiorcy$", tekst_strony)
    role = dict(_rachunki_pionowe(strona))
    if kolejnosc_stron and any(re.match(r"Typ przelewu\b", w, re.I) for w in strona):
        numery = [i for i, w in enumerate(strona) if RACHUNEK_W_TABELI.fullmatch(w)]
        koniec_etykiet = tekst_strony.count("\n", 0, kolejnosc_stron.end())
        if len(numery) == 2 and all(
            koniec_etykiet < i < len(strona) - 1 and re.match(r"[^\W\d_]{2}", strona[i + 1]) for i in numery
        ):
            role = dict(zip(numery, ("Z rachunku", "Na rachunek")))
    i = 0
    while i < len(strona):
        wiersz = daty.get(i, strona[i])
        if kolumny_wyciagu:
            wiersz = re.sub(r"^\. (?=Tytuł:)", "", wiersz, flags=re.I)
        if i in role:
            wiersz = f"{role[i]}: {wiersz}"
        elif i and strona[i - 1].casefold() == "dane zleceniodawcy":
            # W słowie po „Rachunek” zdarzają się błędy OCR. Rolę potwierdza poprzedzający nagłówek.
            rachunek = re.fullmatch(r"Rachunek z\w+[ :]+(.+)", wiersz, re.I)
            if rachunek and RACHUNEK_W_TABELI.fullmatch(rachunek[1]):
                wiersz = f"Z rachunku: {rachunek[1]}"
        nastepny = strona[i + 1] if i + 1 < len(strona) else ""
        i += 1
        naglowek = NAGLOWEK_TABELI.fullmatch(wiersz)
        if naglowek:
            wartosci = WIERSZ_TRANSAKCJI.fullmatch(nastepny)
            if wartosci and bool(naglowek[1]) == bool(wartosci[3]):
                yield "Kwota: " + wartosci[1]
                yield "Data transakcji: " + wartosci[2]
                if wartosci[3]:
                    yield "Numer referencyjny transakcji: " + wartosci[3]
                i += 1
                continue
        # Czasem prawa komórka wpada pomiędzy dwa wiersze lewej etykiety.
        czesc, _, wartosc = wiersz.partition(" ")
        if (czesc.casefold() == "numer" and re.fullmatch(r"transakcji [i|. ]{1,4}", nastepny, re.I)
                and i + 1 < len(strona) and re.match(r"Źródło\b", strona[i + 1], re.I)):
            nastepny = "transakcji"
        if (czesc.casefold(), nastepny.casefold()) in {("numer", "transakcji"), ("data", "wykonania")}:
            yield f"{czesc} {nastepny}: {wartosc}"
            i += 1
            continue
        if kolumny_wyciagu:
            rachunek = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) ((?:z rachunku|na rachunek): .+)", wiersz, re.I)
            if rachunek:
                yield rachunek[1]
                yield rachunek[2]
                continue
            operacja = re.fullmatch(rf"Data operacji\W+przelew [\w -]+? ({KWOTA_Z_WALUTA})", wiersz, re.I)
            if operacja:
                yield "Kwota: " + operacja[1]
                yield "Data operacji"
                continue
        if wiersz.casefold() == "opis kwota":
            operacja = re.fullmatch(rf"przelew [\w -]+? ({KWOTA_Z_WALUTA})", nastepny, re.I)
            if operacja:
                yield "Kwota: " + operacja[1]
                i += 1
                continue
        yield wiersz


def _rachunki_w_sekcjach(wiersze):
    """Odczytaj kolumnę rachunku w blokach danych stron przelewu."""
    for i, wiersz in enumerate(wiersze):
        naglowek = SEKCJA_BANKOWA.fullmatch(wiersz)
        if not naglowek or naglowek[1].casefold() not in {"nadawcy", "odbiorcy"}:
            continue
        if i + 1 >= len(wiersze) or not re.fullmatch(
            r"Nazwa i adres Numer rachunku(?: Nazwa banku)?", wiersze[i + 1], re.I
        ):
            continue
        numery = []
        for komorka in wiersze[i + 2:]:
            if komorka == "\f" or SEKCJA_BANKOWA.fullmatch(komorka):
                break
            numery.extend(RACHUNEK_W_TABELI.findall(komorka))
        if len(numery) == 1:
            pole = "z_rachunku" if naglowek[1].casefold() == "nadawcy" else "na_rachunek"
            yield pole, (numery[0], len(wiersze))


def _pola(wiersze):
    pola = {}
    for indeks, wiersz in enumerate(wiersze):
        for pole, wzorzec in POLA.items():
            dopasowanie = wzorzec.fullmatch(wiersz)
            if dopasowanie:
                wartosc = dopasowanie[1]
                dalsze = indeks + 1
                if (not wartosc and dalsze < len(wiersze) and wiersze[dalsze] != "\f"
                        and not any(p.fullmatch(wiersze[dalsze]) for p in POLA.values())):
                    wartosc = wiersze[dalsze]
                    dalsze += 1
                # Dwa pola o tej samej etykiecie mogą dotyczyć różnych operacji.
                pola[pole] = None if pole in pola else (wartosc or "", dalsze)
    for pole, wartosc in _rachunki_w_sekcjach(wiersze):
        pola[pole] = None if pole in pola else wartosc
    # Przecinek i dalszy opis właściciela wyznaczają koniec numeru także po złamaniu wiersza.
    tekst = "\n".join(wiersze)
    for pole, wzorzec in RACHUNKI_W_ZDANIU.items():
        for m in wzorzec.finditer(tekst):
            if RACHUNEK_W_TABELI.fullmatch(normalize_spaces(m[1])):
                pola[pole] = None if pole in pola else (m[1], len(wiersze))
    return pola


def _rachunek(wartosc, dalsze, wiersze):
    wartosc = re.sub(r"^>\s*|\s+[.©]$", "", wartosc)
    numer = FORMATTERS["bank-account"](wartosc)
    if not re.fullmatch(r"(?:[A-Za-z]{2}(?:[0-9][A-Za-z0-9]*)?|[0-9]+)", numer):
        return None
    krajowy = numer[:2].upper() == "PL" or numer[0].isdigit()
    wzorzec = RACHUNEK_KRAJOWY if krajowy else FOREIGN_IBAN
    for indeks in range(dalsze, len(wiersze)):
        wiersz = wiersze[indeks]
        if wiersz == "\f":
            # Pełny numer może kończyć stronę. Nie łącz jego fragmentów przez podział strony.
            if (krajowy and len(numer.upper().removeprefix("PL")) == 24 and indeks + 1 < len(wiersze)
                    and wiersze[indeks + 1].replace(" ", "").isdigit()):
                return None
            break
        dalszy_numer = FORMATTERS["bank-account"](wiersz)
        if wzorzec.fullmatch(numer):
            # Samodzielny dalszy ciąg cyfr czyni granicę wartości niejednoznaczną.
            return None if dalszy_numer.isdigit() else numer
        if not re.fullmatch(r"[0-9]+" if krajowy else r"[A-Z0-9]+", dalszy_numer):
            break
        numer += dalszy_numer
        if len(numer) > 34:
            return None
    return numer if wzorzec.fullmatch(numer) else None


def _kwota(wartosc, waluta):
    dopasowanie = KWOTA.fullmatch(wartosc)
    if not dopasowanie:
        return None
    jawna_waluta = dopasowanie[1] or dopasowanie[3]
    if waluta is not None and waluta.casefold() not in {"pln", "zł"}:
        return None
    if not jawna_waluta and not waluta:
        return None
    liczba = dopasowanie[2].replace(" ", "").replace(",", ".")
    kwota = float(liczba)
    return kwota if Decimal(str(kwota)) == Decimal(liczba) else None


def _numer_transakcji(wartosc):
    wartosc = wartosc.removesuffix(".")
    kod = re.fullmatch(r"[A-Z0-9]+(?:[._/-][A-Z0-9]+)*", wartosc, re.IGNORECASE)
    return wartosc if kod and re.search(r"[0-9]", wartosc) else None


def _tytul(wartosc, dalsze, wiersze, numer_transakcji):
    zamkniecie = QUOTE_PAIRS.get(wartosc[:1])
    if not zamkniecie:
        if not wartosc or ETYKIETA_FORMULARZA.fullmatch(wartosc) or re.search(r":|\.{2,}", wartosc):
            return None
        fragmenty = [wartosc]
        for wiersz in wiersze[dalsze:]:
            if STOPKA_BANKU.match(wiersz):
                return " ".join(fragmenty)
            if wiersz.casefold() == "typ transakcji przelew z rachunku":
                return " ".join(fragmenty)
            if ETYKIETA_FORMULARZA.fullmatch(wiersz):
                # Ostatni token wielowierszowej wartości ma dodatkowe potwierdzenie w osobnym polu.
                if len(fragmenty) == 1 or fragmenty[-1].split()[-1] == numer_transakcji:
                    return " ".join(fragmenty)
                return None
            if wiersz == "\f" or re.search(r":|\.{2,}", wiersz):
                return None
            if wiersz != numer_transakcji and not ODSYLACZ.search(wiersz):
                return None
            fragmenty.append(wiersz)
        return None
    fragmenty = [wartosc[1:]]
    while zamkniecie not in fragmenty[-1] and dalsze < len(wiersze):
        wiersz = wiersze[dalsze]
        if wiersz == "\f" or ETYKIETA_FORMULARZA.fullmatch(wiersz):
            return None
        fragmenty.append(wiersz)
        dalsze += 1
    tytul, znak, reszta = " ".join(fragmenty).partition(zamkniecie)
    if not znak or reszta.strip() not in {"", "."} or wartosc[0] in tytul:
        return None
    return tytul.strip() or None


class przelew:
    @staticmethod
    def zastosuj(tekst: str, wynik: dict) -> None:
        dane = wynik.get("przelew_bankowy") if isinstance(wynik, dict) else None
        if not isinstance(dane, dict):
            return
        wiersze = _wiersze(tekst)
        pola = _pola(wiersze)
        referencja = pola.get("numer_transakcji")
        numer_transakcji = _numer_transakcji(referencja[0]) if referencja else None
        for pole, zrodlo in pola.items():
            if not zrodlo or pole not in dane or pole == "waluta":
                continue
            typy = (int, float) if pole == "kwota" else (str,)
            if dane[pole] is not None and type(dane[pole]) not in typy:
                continue
            wartosc, dalsze = zrodlo
            if pole in {"na_rachunek", "z_rachunku"}:
                wartosc = _rachunek(wartosc, dalsze, wiersze)
            elif pole == "kwota":
                waluta = pola.get("waluta")
                if "waluta" in pola and not waluta:
                    continue
                wartosc = _kwota(wartosc, waluta[0] if waluta else None)
            elif pole == "data_operacji":
                try:
                    wartosc = date.fromisoformat(FORMATTERS["date-iso"](wartosc)).isoformat()
                except ValueError:
                    continue
            elif pole == "numer_transakcji":
                wartosc = numer_transakcji
            elif pole == "tytul":
                wartosc = _tytul(wartosc, dalsze, wiersze, numer_transakcji)
            if wartosc is not None:
                dane[pole] = wartosc

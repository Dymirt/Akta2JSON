import re
from datetime import date

from odwolania.templates import FORMATTERS


_NAGLOWEK = re.compile(
    r"^[ \t]*(?:§[ \t]*\d+\.[ \t]*)?"
    r"(mocodawca|pełnomocnik|pełnomocnicy|zamawiający|postępowanie|zakres|podpisy)"
    r"[ \t]*(?::|$)",
    re.IGNORECASE | re.MULTILINE,
)
_SPOLKA_KAPITALOWA = re.compile(
    r"\b(?:S\.\s*A\.|sp\.\s*z\s*o\.\s*o\.|spółka (?:akcyjna|z ograniczoną odpowiedzialnością))$",
    re.IGNORECASE,
)
_LINIA_PODPISU = re.compile(r"(?:\.{3,}|…+|_{3,})")
_CZLON = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+"
_OSOBA = re.compile(rf"{_CZLON}(?:-{_CZLON})?(?: {_CZLON}(?:-{_CZLON})?){{1,2}}")
_FUNKCJA = re.compile(
    r"(?:prezes|wiceprezes|członek) zarządu(?: komplementariusza)?|prokurent|dyrektor|wspólnik",
    re.IGNORECASE,
)
_W_IMIENIU = re.compile(r"W imieniu (.+):", re.I)
_ZA = re.compile(r"Za (.+)", re.I)
_RUBRYKA = re.compile(r"(?:imię|imiona) (?:i )?nazwisk[oa]|podpis (?:mocodawcy|osoby uprawnionej)", re.I)
_TYTUL_PELNOMOCNIKA = re.compile(r"(?:adw\.|r\.\s*pr\.)\s+", re.I)
_WZOR_PODPISU = re.compile(r"\b(?:wzór|wzory|przykład) podpis(?:u|ów)\b", re.I)
_SEPARATOR_OPISU = re.compile(r"\s*,\s*|\s+[–—-]\s+")
_WPIS = r"(?:nr\.?|numer) wpisu(?: na listę)?\s*:?\s*(?:[A-Z]{1,5}[- /])?[0-9]{2,8}"
_OPIS_OSOBY = re.compile(
    rf"(?:(?:{_FUNKCJA.pattern})(?:\s+[–—-]\s+lider konsorcjum)?"
    rf"|(?:adwokat|radca prawny)(?:[,.]\s*{_WPIS})?|{_WPIS})[.,]?", re.I,
)


def _czy_nazwisko(osoba):
    return bool(_OSOBA.fullmatch(osoba) and not _RUBRYKA.fullmatch(osoba) and not _FUNKCJA.fullmatch(osoba))


def _oddziel_funkcje_od_nazwisk(tekst, wartosc):
    if isinstance(wartosc, list):
        for rekord in wartosc:
            _oddziel_funkcje_od_nazwisk(tekst, rekord)
    elif isinstance(wartosc, dict):
        for pole, rekord in wartosc.items():
            if pole == "imie_nazwisko" and isinstance(rekord, str):
                czesci = _SEPARATOR_OPISU.split(" ".join(rekord.split()), maxsplit=1)
                if len(czesci) == 2 and _czy_nazwisko(czesci[0]) and _OPIS_OSOBY.fullmatch(czesci[1]):
                    if re.search(r"(?<![\w-])" + re.escape(czesci[0]) + r"(?![\w-])", tekst):
                        wartosc[pole] = czesci[0]
            elif isinstance(rekord, (dict, list)):
                _oddziel_funkcje_od_nazwisk(tekst, rekord)


def _inny_podpis_lub_wzor(wiersz):
    if _FUNKCJA.fullmatch(wiersz) or _WZOR_PODPISU.search(wiersz):
        return True
    czesci = re.split(r"\s*,\s*|\s+[–—-]\s+", wiersz, maxsplit=1)
    return len(czesci) == 2 and _czy_nazwisko(czesci[0]) and bool(_FUNKCJA.fullmatch(czesci[1]))


def _podpisy(tekst, mocodawcy, jedyny=None):
    """Zastąp listy dopiero po przypisaniu całego bloku podpisów wszystkim mocodawcom."""
    rekordy = {}
    for rekord in mocodawcy:
        if not isinstance(rekord, dict) or not isinstance(rekord.get("data"), dict):
            return
        nazwa, lista = rekord["data"].get("nazwa"), rekord.get("podpisujacy")
        if not isinstance(nazwa, str) or not nazwa.strip() or not isinstance(lista, list):
            return
        if any(not isinstance(osoba, dict) or osoba.keys() != {"imie_nazwisko"} for osoba in lista):
            return
        klucz = " ".join(nazwa.split()).casefold()
        if klucz in rekordy:
            return
        rekordy[klucz] = rekord

    wiersze = [" ".join(w.split()) for w in tekst.splitlines() if w.strip()]
    przyjecia = [i for i, w in enumerate(wiersze) if w.casefold() == "pełnomocnictwo przyjmuję:"]
    if przyjecia:
        koniec = przyjecia[0]
        if len(przyjecia) != 1:
            return
        for wiersz in wiersze[koniec + 1:]:
            if _LINIA_PODPISU.fullmatch(wiersz):
                continue
            tytul = _TYTUL_PELNOMOCNIKA.match(wiersz)
            if not tytul or not _czy_nazwisko(wiersz[tytul.end():]):
                return
        wiersze = wiersze[:koniec]
    pierwsza = next((i for i, w in enumerate(wiersze) if _LINIA_PODPISU.fullmatch(w)), None)
    if pierwsza is None or any(_inny_podpis_lub_wzor(w) for w in wiersze[:pierwsza]):
        return
    i = pierwsza
    naglowek = wiersze[i - 1] if i else ""
    wlasciciel = jedyny if naglowek.casefold() == "mocodawca:" else None
    if _W_IMIENIU.fullmatch(naglowek):
        i -= 1
    if any(_W_IMIENIU.fullmatch(w) for w in wiersze[:i]):
        return
    podpisy = {}
    while i < len(wiersze):
        grupa = _W_IMIENIU.fullmatch(wiersze[i])
        if grupa:
            wlasciciel = grupa[1].casefold()
            i += 1
        if i >= len(wiersze) or not _LINIA_PODPISU.fullmatch(wiersze[i]):
            return
        i += 1
        # „Za X” wskazuje właściciela tylko bieżącego podpisu.
        za = _ZA.fullmatch(wiersze[i]) if i < len(wiersze) else None
        klucz = za[1].casefold() if za else wlasciciel
        if za:
            if wlasciciel is not None and klucz != wlasciciel:
                return
            i += 1
        if klucz not in rekordy or i + 1 >= len(wiersze):
            return
        osoba, funkcja = wiersze[i:i + 2]
        if not _czy_nazwisko(osoba) or not _FUNKCJA.fullmatch(funkcja):
            return
        lista = podpisy.setdefault(klucz, [])
        if osoba in lista:
            return
        lista.append(osoba)
        i += 2
    if podpisy.keys() == rekordy.keys():
        for klucz, osoby in podpisy.items():
            rekordy[klucz]["podpisujacy"] = [{"imie_nazwisko": osoba} for osoba in osoby]


def _nazwa_w_deklaracji(tekst, mocodawcy):
    """Potwierdź nazwę i oddziel adres wprost w definicji spółki o zgodnym KRS i NIP."""
    if len(mocodawcy) != 1 or not isinstance(mocodawcy[0], dict):
        return
    dane = mocodawcy[0].get("data")
    if not isinstance(dane, dict) or not isinstance(dane.get("nazwa"), str):
        return
    wpis = " ".join(dane["nazwa"].split())
    firma, przecinek, adres = wpis.partition(",")
    if not _SPOLKA_KAPITALOWA.search(firma):
        return
    definicje = list(re.finditer(r'\(dalej\s*:\s*[„"«]mocodawca[”"»]\)', tekst, re.I))
    if len(definicje) != 1:
        return
    wzorzec_firmy = r"\s+".join(map(re.escape, firma.split()))
    deklaracja = re.search(
        r"(?:^[ \t]*pełnomocnictwo(?: procesowe| ogólne| szczególne)?[ \t]*\r?\n\s*|\bmocodawcą\s+jest\s+)"
        rf"(?P<firma>{wzorzec_firmy}),\s*(?P<adres>(?:ul\.|al\.)\s+[^,;()]+,\s*[0-9]{{2}}-[0-9]{{3}}\s+[^,;()\d]+)"
        r",\s*KRS\s*:?\s*(?P<krs>[0-9]{10}),\s*NIP\s*:?\s*(?P<nip>[0-9]{10})"
        r"(?:,\s*REGON\s*:?\s*(?:[0-9]{14}|[0-9]{9}))?\s*\Z", tekst[:definicje[0].start()], re.I | re.M,
    )
    if not deklaracja or any(deklaracja[pole] != dane.get(pole) for pole in ("krs", "nip")):
        return
    if przecinek and adres.strip().casefold() != " ".join(deklaracja["adres"].split()).casefold():
        return
    dane["nazwa"] = " ".join(deklaracja["firma"].split())
    return dane["nazwa"].casefold()


def _rejestr_jedynego_mocodawcy(tekst, mocodawcy):
    if len(mocodawcy) != 1 or not isinstance(mocodawcy[0], dict):
        return None
    dane = mocodawcy[0].get("data")
    if not isinstance(dane, dict) or not isinstance(dane.get("nazwa"), str) or not dane["nazwa"].strip():
        return

    tekst = tekst.replace("\r\n", "\n")
    naglowki = list(_NAGLOWEK.finditer(tekst))
    sekcje = [
        tekst[a.end():b.start()].strip() for a, b in zip(naglowki, naglowki[1:])
        if a[1].lower() == "mocodawca" and b[1].lower() in {"pełnomocnik", "pełnomocnicy"}
    ]
    if len(sekcje) != 1:
        return
    sekcja = sekcje[0]
    nazwa = " ".join(dane["nazwa"].split())
    wzorzec_nazwy = r"\s+".join(map(re.escape, nazwa.split()))
    poczatek_rejestru = r",?\s+(?:ul\.|al\.|KRS\b|NIP\b|dane\s+rejestrowe\b)"
    if not re.match(r"(?:Mocodawcą\s+jest\s+)?" + wzorzec_nazwy + poczatek_rejestru, sekcja, re.I):
        return

    potwierdzone = 0
    for pole in ("krs", "nip"):
        etykieta = rf"\b{pole}\b"
        numer = re.search(etykieta + r"\s*:?\s*([0-9]{10})(?![\w-])", sekcja, re.I)
        if numer and len(re.findall(etykieta, sekcja, re.I)) == 1:
            potwierdzone += 1
            if pole in dane:
                dane[pole] = numer[1]
    if "typ" in dane and _SPOLKA_KAPITALOWA.search(nazwa):
        dane["typ"] = "osoba_prawna"
    # Nienazwana rubryka „Mocodawca:” wymaga jednej sekcji rejestrowej jednego podmiotu.
    if potwierdzone == 2:
        return nazwa.casefold()
    return None


def _popraw_funkcje_przy_podpisie(tekst, mocodawcy, jedyny):
    """W stopce z jednym podpisem usuń funkcję wpisaną jako druga osoba."""
    if not jedyny or len(mocodawcy) != 1:
        return
    osoby = mocodawcy[0].get("podpisujacy")
    if not isinstance(osoby, list) or len(osoby) != 2:
        return
    wiersze = [" ".join(w.split()) for w in tekst.splitlines() if w.strip()]
    if len(wiersze) < 6:
        return
    etykieta, dzien, linia, nazwisko, funkcja, pieczec = wiersze[-6:]
    if etykieta.casefold() != "data" or pieczec.casefold() != "(podpis i pieczęć)" or not _LINIA_PODPISU.fullmatch(linia):
        return
    if not _czy_nazwisko(nazwisko) or not _FUNKCJA.fullmatch(funkcja):
        return
    # Inny blok podpisów (również przyjęcie pełnomocnictwa) czyni przypisanie stopki niejednoznacznym.
    if any(_LINIA_PODPISU.fullmatch(w) or _inny_podpis_lub_wzor(w) or _W_IMIENIU.fullmatch(w) or _ZA.fullmatch(w)
           or w.casefold().startswith(("podpis", "pełnomocnictwo przyjmuję")) for w in wiersze[:-6]):
        return
    try:
        date.fromisoformat(FORMATTERS["date-iso"](dzien))
    except ValueError:
        return
    osoba = {"imie_nazwisko": nazwisko}
    stanowisko = {"imie_nazwisko": funkcja}
    if osoba in osoby and stanowisko in osoby:
        osoby.remove(stanowisko)


class pelnomocnictwo:
    @staticmethod
    def zastosuj(tekst: str, wynik: dict) -> None:
        mocodawcy = wynik.get("mocodawca")
        if isinstance(mocodawcy, list) and mocodawcy:
            z_deklaracji = _nazwa_w_deklaracji(tekst, mocodawcy)
            jedyny = _rejestr_jedynego_mocodawcy(tekst, mocodawcy)
            _podpisy(tekst, mocodawcy, jedyny or z_deklaracji)
            _popraw_funkcje_przy_podpisie(tekst, mocodawcy, jedyny)
        _oddziel_funkcje_od_nazwisk(" ".join(tekst.split()), wynik)

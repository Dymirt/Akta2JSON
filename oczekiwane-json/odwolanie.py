"""Jawne dane z nagłówka odwołania i rozdzielenie listy pełnomocników."""

import re
import unicodedata
from datetime import date

from odwolania.templates import FORMATTERS, HEADER_LINES, POLISH_MONTHS, QUOTE_PAIRS


_KONIEC_NAGLOWKA = re.compile(
    r"^(?:działając\b|wnoszę odwołanie\b|uzasadnienie\b|zarzut\b|strona 1 z \d+$)", re.I
)
_MIESIACE = "|".join(POLISH_MONTHS)
_DATA = rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}} (?:{_MIESIACE}) \d{{4}})"
_CZLON_NAZWY = r"[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]*"
_MIEJSCOWOSC = rf"{_CZLON_NAZWY}(?:(?:-| (?:nad |pod |na )?){_CZLON_NAZWY})*"
_WIERSZ_DATY = re.compile(
    rf"(?:(?P<etykieta>(?i:data(?: wniesienia odwołania| pisma)?)\s*:)\s*|"
    rf"(?!(?i:dnia|data|termin|odwołanie|sporządzono|podpisano)\b)(?P<miejsce>{_MIEJSCOWOSC})(?:,\s*|\s+))?"
    rf"(?i:(?:dnia )?(?P<data>{_DATA})(?: (?:r\.?|roku))?)"
)
_TYTUL = re.compile(
    r"\bzamówieni(?:a|e|u)\b[^:;„“”\"«»]{0,180}?\b(?:pn\.|pod nazwą)\s*"
    r"(?P<otwarcie>[„“\"«»])(?P<tytul>[^„“”\"«»]+)(?P<zamkniecie>[”\"»«])"
    r"\s*[,;]?\s*(?:nr\.?|numer) referencyjny\b",
    re.I,
)
_ETYKIETA_TED = re.compile(
    r"\b(?:TED|ogłoszeni[ae]\s+(?:o\s+zamówieniu\s+)?w\s+Dzienniku\s+Urzędowym\s+(?:UE|Unii\s+Europejskiej))"
    r"\s*(?::|nr\b)\s*", re.I,
)
_NUMER_TED = re.compile(r"(?<![\w/-])(?:[0-9]{4}/S\s*[0-9]{3}-[0-9]{6}|[0-9]{6}-[0-9]{4})(?![\w/-])", re.I)
_ZRODLO_TED = re.compile(r"\bTED\b|\bDzienniku\s+Urzędowym\s+(?:UE|Unii\s+Europejskiej)\b", re.I)
_HISTORYCZNE = r"(?:poprzedni\w*|wcześniejsz\w*|archiwaln\w*|historyczn\w*|inn(?:ego|ym|e|ej))"
_PRZEDMIOT_WZMIANKI = r"(?:ogłoszeni|postępowani|zamówieni)\w*"
_INNE_OGLOSZENIE = re.compile(
    rf"\b(?:{_HISTORYCZNE}\s+{_PRZEDMIOT_WZMIANKI}|{_PRZEDMIOT_WZMIANKI}\s+{_HISTORYCZNE})\b",
    re.I,
)
_NAGLOWEK_ODWOLUJACEGO = re.compile(r"^[ \t]*Odwołując[ya](?:[ \t]+(?:nr\.?[ \t]*)?[0-9]+)?[ \t]*:", re.I | re.M)
_ODWOLUJACY = re.compile(
    r"^Odwołujący:[^\n]*\n(.*?)(?=^(?:Odwołujący\b|Zamawiający\b|Przystępując\w*\b|Uczestni\w*\b|Dotyczy:)|\Z)",
    re.I | re.M | re.S,
)
_WYZNACZENIE_KONTAKTU = re.compile(
    r"(?<![\w@.])kontakt(?:u|ow\w*)?(?![\w@.])|\bdoręcz\w*|\bdo\s+odbioru\s+(?:pism|korespondencji)\b|"
    r"\bkorespondencj[ęa]\s+(?:prosimy\s+)?(?:kierow|adresow|wysyła)\w*|\b(?:na\s+ręce|do\s+rąk)\b", re.I,
)
_ETYKIETA_OSOBY = r"osoba do (?:kontaktu|doręczeń)"
_REPREZENTACJA = re.compile(
    rf"^reprezentowan[ayi] przez( pełnomocnik(?:a|ów))?:\s*(.*?)"
    rf"(?=\n(?:(?:adres do korespondencji|{_ETYKIETA_OSOBY})\s*:|kancelaria\b))",
    re.I | re.M | re.S,
)
_TYTUL_ZAWODOWY = r"(?i:adw\.|adwokat|r\.\s*pr\.|radca prawny)"
_NAZWISKO = rf"{_CZLON_NAZWY}(?:-{_CZLON_NAZWY})?"
_ADWOKAT_LUB_RADCA = re.compile(rf"{_TYTUL_ZAWODOWY}\s+({_NAZWISKO}(?: {_NAZWISKO}){{1,3}})")
_OSOBA_DO_KONTAKTU = re.compile(
    rf"^[ \t]*{_ETYKIETA_OSOBY}[ \t]*:[ \t]*(?:{_TYTUL_ZAWODOWY}[ \t]+)?([^\r\n]+)", re.I | re.M,
)


_DATA_W_TRESCI = re.compile(rf"(?<!\w){_DATA}(?!\w)", re.I)
_PIERWSZY_PUNKT_Z_DATA = re.compile(
    r"\b(?:czynności(?: i zaniechań)?|zaniechań) Zamawiającego,? polegających na:\s*1\)\s*"
    r"([^;]{1,650});(?=\s*(?:Strona \d+ z \d+\s*)?2\))", re.I,
)
_ETYKIETA_ZAWIADOMIENIA = r"\b(?:informacj[ęa]|zawiadomieni[ea]) o zaskarżonej czynności"
_DATA_ZAWIADOMIENIA = re.compile(
    rf"{_ETYKIETA_ZAWIADOMIENIA} (?:(?:został[ao] )?(?:przekazan[aeo]|doręczon[aeo]|opublikowan[aeo])|otrzymano) "
    rf"(?:Odwołującemu )?(?:w dniu |dnia )?({_DATA})(?!\w)", re.I,
)
_WNOSZE_O = re.compile(
    r"(?:^[ \t]*(?:działając w imieniu (?:wykonawcy|odwołującego) )?|,[ \t]*)wnoszę\s+o\s*:", re.I | re.M,
)
_DEKLARACJA = re.compile(
    rf"Zamawiający w dniu (?P<dzien>{_DATA})(?: roku| r\.?)? (?P<zdarzenie>[^.;:!?]+)\.", re.I,
)
_KONIEC_ZARZUTU = re.compile(
    r"^[ \t]*(?:Zarzut\s+(?:nr\.?\s+)?[1-9]\d*\b|Wnoszę\s+o\s*:|Załączniki\s*:)", re.I | re.M,
)
_NIEJEDNOZNACZNA_DATA_PUNKTU = re.compile(
    rf"\b(?:lub|albo|ewentualnie|ustawy z dnia)\b|\b\d{{1,2}}\s*(?:[–—-]|i|oraz)\s*\d{{1,2}} (?:{_MIESIACE})\b", re.I,
)
_INNA_ROLA_DATY = re.compile(
    rf"\bZamawiający w dniu (?P<dzialanie>{_DATA})(?= (?:roku|r\.) "
    r"(?:unieważni+ł postępowanie|udostępnił opis przedmiotu zamówienia|odrzucił ofertę|ogłosił wybór oferty)\.(?: |$))|"
    rf"(?<!\w)(?P<kopia>{_DATA}) (?:r\. )?Przekazanie kopii odwołania Zamawiającemu\b", re.I,
)
_SLAD_DATOWNIKA = re.compile(
    rf"\b(?:{_MIESIACE}|dnia|data pisma|data wniesienia)\b|\b\d{{1,2}}\s*[./-]\s*\d{{1,2}}\s*[./-]\s*\d{{2,4}}\b|"
    r"\b\d{1,2} [IVX]+ \d{4}\b", re.I,
)


def _deklaracja_przed_zarzutem(tekst):
    """Wydziel pojedynczą datowaną czynność z petitum poprzedzającego pierwszy zarzut."""
    zarzuty = list(_PIERWSZY_ZARZUT.finditer(tekst))
    if len(zarzuty) != 1:
        return None
    zarzut = zarzuty[0]
    otwarcie = tekst[:zarzut.start()]
    wnioski = list(_WNOSZE_O.finditer(otwarcie))
    if len(wnioski) != 1 or _PIERWSZA_CZYNNOSC.search(otwarcie):
        return None
    przed_wnioskiem = otwarcie[:wnioski[0].start()]
    if re.search(r"\bnie\s*$|\b(?:cytuję|cytujemy|zacytowano|zacytuję|przytoczono)\b", przed_wnioskiem, re.I):
        return None
    # Sam nagłówek „ODWOŁANIE” i rubryka „Dotyczy” mogą znaleźć się w kolejnych wierszach.
    bez_naglowka = re.sub(r"(?im)^[ \t]*odwołanie[ \t]*$", "", przed_wnioskiem)
    wstep = " ".join(bez_naglowka.split())
    if re.search(r"\bodwołanie (?:od|na|wobec)\b", wstep, re.I) or _OSOBNE_WSKAZANIE_CZYNNOSCI.search(wstep):
        return None
    if re.search(r"(?im)^[ \t]*(?:załącznik(?:i|\s+nr\.?\s*\d+)?|wzór|przykład|cytat|uzasadnienie)\b", otwarcie):
        return None
    zdanie = " ".join(otwarcie[wnioski[0].end():].split())
    deklaracja = _DEKLARACJA.fullmatch(zdanie)
    if not deklaracja:
        return None
    try:
        dzien = date.fromisoformat(FORMATTERS["date-iso"](deklaracja["dzien"])).isoformat()
    except ValueError:
        return None
    pierwszy = _KONIEC_ZARZUTU.split(tekst[zarzut.end():], maxsplit=1)[0]
    tytul = re.match(r"([^.:;!?]{1,300}):", pierwszy)
    if not tytul:
        return None
    daty_w_zarzucie = {FORMATTERS["date-iso"](m[0]) for m in _DATA_W_TRESCI.finditer(" ".join(pierwszy.split()))}
    if daty_w_zarzucie - {dzien}:
        dzien = None
    return deklaracja["zdarzenie"], dzien, " ".join(tytul[1].split()), pierwszy


def _daty_czynnosci_i_pisma(tekst, naglowek, dane, deklaracja):
    tresc = " ".join(tekst.split())
    normalizuj = FORMATTERS["date-iso"]
    if "czynnosc_dzien" in dane and dane["czynnosc_dzien"] is None:
        punkty = _PIERWSZY_PUNKT_Z_DATA.findall(tresc)
        zawiadomienia = _DATA_ZAWIADOMIENIA.findall(tresc)
        w_zawiadomieniu = {normalizuj(d) for d in zawiadomienia}
        if len(punkty) == 1 and not _NIEJEDNOZNACZNA_DATA_PUNKTU.search(punkty[0]):
            w_zarzucie = {normalizuj(m[0]) for m in _DATA_W_TRESCI.finditer(punkty[0])}
            if len(w_zarzucie) == 1 and w_zarzucie == w_zawiadomieniu:
                kandydat = w_zarzucie.pop()
                try:
                    dane["czynnosc_dzien"] = date.fromisoformat(kandydat).isoformat()
                except ValueError:
                    pass
        elif deklaracja and deklaracja[2] is not None:
            etykiety = re.findall(_ETYKIETA_ZAWIADOMIENIA, tresc, re.I)
            if len(etykiety) == len(zawiadomienia) and not (w_zawiadomieniu - {deklaracja[2]}):
                dane["czynnosc_dzien"] = deklaracja[2]

    data_pisma = dane.get("data")
    poczatek_tresci = re.search(r"(?im)^[ \t]*Działając\b", tekst)
    if not isinstance(data_pisma, str) or not poczatek_tresci:
        return
    data_pisma = normalizuj(data_pisma.strip())
    # Sprawdzamy również nietypowe zapisy daty oraz datowniki, których dotychczasowa reguła nie odczytała.
    if not any("".join(w.split()).casefold() == "odwołanie" for w in naglowek):
        return
    naglowek_pisma = " ".join(naglowek)
    if naglowek_pisma != " ".join(tekst[:poczatek_tresci.start()].split()):
        return
    if _SLAD_DATOWNIKA.search(naglowek_pisma) or _DATA_W_TRESCI.search(naglowek_pisma):
        return
    if re.search(r"\b(?:tego samego dnia|tego dnia|w tym samym dniu)\b", tresc, re.I):
        return
    wystapienia = {m.span() for m in _DATA_W_TRESCI.finditer(tresc) if normalizuj(m[0]) == data_pisma}
    inne_role = {m.span(m.lastgroup) for m in _INNA_ROLA_DATY.finditer(tresc)}
    if wystapienia and wystapienia <= inne_role:
        dane["data"] = None


def _naglowek(tekst):
    wiersze = []
    for wiersz in tekst.split("\f", 1)[0].splitlines():
        wiersz = " ".join(wiersz.split())
        if _KONIEC_NAGLOWKA.match(wiersz) or len(wiersze) == HEADER_LINES:
            break
        if wiersz:
            wiersze.append(wiersz)
    return wiersze


def _wpisz(obiekt, klucz, wartosc):
    if wartosc is not None and klucz in obiekt and (obiekt[klucz] is None or isinstance(obiekt[klucz], str)):
        obiekt[klucz] = wartosc


def _rozdziel_pelnomocnikow(naglowek, tekst, strony):
    if not isinstance(strony, list) or len(strony) > 1:
        return
    osoba = strony[0].get("pelnomocnik") if strony and isinstance(strony[0], dict) else {}
    if not isinstance(osoba, dict):
        return
    tekst = "\n".join(tekst.splitlines())
    if len(_NAGLOWEK_ODWOLUJACEGO.findall(tekst)) != 1:
        return
    sekcje = _ODWOLUJACY.findall(naglowek)
    listy = _REPREZENTACJA.findall(sekcje[0]) if len(sekcje) == 1 else []
    if len(listy) != 1:
        return
    rola, lista = listy[0]
    osoby = [_ADWOKAT_LUB_RADCA.fullmatch(wpis.strip()) for wpis in re.split(r",\s*|\n", lista)]
    if not all(osoby) or (len(osoby) < 2 and not rola):
        return
    nazwy = [osoba_z_listy[1] for osoba_z_listy in osoby]
    for nazwa in nazwy:
        if re.search(r"adres do korespondencji:\s*(?:" + _TYTUL_ZAWODOWY + r"\s+)?" + re.escape(nazwa) + r"\b",
                     naglowek, re.I):
            return
    aktualna = osoba.get("imie_nazwisko")
    if aktualna is None and not rola:
        return
    wybrana = nazwy[0]
    kontakt = _OSOBA_DO_KONTAKTU.search(sekcje[0])
    if kontakt:
        wybrana = kontakt[1].strip().removesuffix(".")
        if wybrana not in nazwy:
            return
        tekst = _OSOBA_DO_KONTAKTU.sub("", tekst, count=1)
    if _WYZNACZENIE_KONTAKTU.search(tekst):
        return
    if aktualna is not None:
        if not isinstance(aktualna, str):
            return
        podana = " ".join(re.sub(_TYTUL_ZAWODOWY + "|,", " ", aktualna).split())
        if podana != " ".join(nazwy) and not (kontakt and podana in nazwy):
            return
    if not strony:
        # Model może pominąć całą listę. Powiąż pełnomocnika tylko z nazwanym, pojedynczym odwołującym.
        podpis = re.search(r"(?im)^Odwołujący: +([^\n]+)$", naglowek)
        if not podpis or re.search(r"\bkonsorcjum\b", podpis[1], re.I):
            return
        potwierdzenie = r"\bdziałając w imieniu odwołującego\s*[–—-]\s*" + re.escape(podpis[1]) + r"\s*\(dalej:"
        if not re.search(potwierdzenie, tekst, re.I):
            return
        osoba = {"imie_nazwisko": None, "nazwa": None, "mail": None}
        strony.append({"nazwa": podpis[1], "krs": None, "nip": None, "regon": None,
                       "przez-pelnomocnika": 1, "pelnomocnik": osoba})
    osoba["imie_nazwisko"] = wybrana


def _mail_pelnomocnika_z_ocr(naglowek, tekst, strony):
    if not isinstance(strony, list) or len(strony) != 1 or not isinstance(strony[0], dict):
        return
    osoba = strony[0].get("pelnomocnik")
    if not isinstance(osoba, dict) or not isinstance(osoba.get("imie_nazwisko"), str):
        return
    # Popraw tylko wadliwy separator. Zachowaj odczytany przez model kompletny adres.
    if isinstance(osoba.get("mail"), str) and "@" in osoba["mail"]:
        return
    imie_nazwisko = osoba["imie_nazwisko"].strip()
    nazwa_ascii = unicodedata.normalize("NFKD", imie_nazwisko.casefold().replace("ł", "l"))
    nazwa_ascii = "".join(c for c in nazwa_ascii if not unicodedata.combining(c))
    czlony = nazwa_ascii.split()
    if len(czlony) != 2 or not all(re.fullmatch(r"[a-z]+(?:-[a-z]+)*", c) for c in czlony):
        return
    # Szukamy po imiennej rubryce prawnika, wyłącznie w bloku odwołującego.
    bloki = re.split(r"(?im)^[„\" ]*odwołując[ya]\s*:", naglowek)
    if len(bloki) != 2:
        return
    blok = re.split(r"(?im)^(?:zamawiający|przystępujący|dotyczy|odwołanie)\b", bloki[1], maxsplit=1)[0]
    nazwany = re.search(r"(?im)^(?:adw\.|adwokat|radca prawny|r\. *pr\.) +" + re.escape(imie_nazwisko)
                        + r"[^\w\n]*$", blok)
    if not nazwany:
        return
    lokalna = re.escape(f"{czlony[0][0]}.{czlony[1]}")
    etykieta = r"(?im)^e-?mail *: *(.*)$"
    domena = r"(?:[a-zA-Z0-9](?:[-a-zA-Z0-9]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}"
    wzorzec = re.compile(rf"((?i:{lokalna})) *(Q|©|\(OQ|\(a|a) *({domena})", re.ASCII)
    adresy = set()
    for wartosc in re.findall(etykieta, blok[nazwany.end():]):
        if "@" in wartosc:
            return
        dopasowanie = wzorzec.fullmatch(wartosc.strip())
        if dopasowanie:
            konto, separator, host = dopasowanie.groups()
            if separator == "a" and not re.search(r"\bwww\s*\.\s*" + re.escape(host) + r"(?![\w.-])", tekst, re.I):
                continue
            adresy.add(f"{konto}@{host}")
    if len(adresy) == 1:
        _wpisz(osoba, "mail", adresy.pop())


def _numer_ted(naglowek):
    opis = re.split(r"(?im)^dotyczy\s*:", naglowek)
    if len(opis) != 2:
        return None
    opis = re.split(r"(?im)^(?:zamawiający\b|odwołujący\b|wartość zamówienia:|wpis od odwołania:|odwołanie\b)",
                    opis[1], maxsplit=1)[0]
    opis = opis.strip()
    if not re.match(r"postępowania\s+o\s+udzielenie\s+zamówienia\b", opis, re.I):
        return None
    if len(_ZRODLO_TED.findall(opis)) != 1 or _INNE_OGLOSZENIE.search(opis):
        return None
    etykiety = list(_ETYKIETA_TED.finditer(opis))
    numery = list(_NUMER_TED.finditer(opis))
    if len(etykiety) != 1 or len(numery) != 1 or numery[0].start() != etykiety[0].end():
        return None
    if not re.search(r"(?:[,;]|\n)\s*(?:numer(?:\s+ogłoszenia)?\s+)?$", opis[:etykiety[0].start()], re.I):
        return None
    koniec_wiersza = opis[numery[0].end():].partition("\n")[0].strip()
    kolejne_pole = re.match(r"[,;]\s*(?:nr\.?|numer)\s+(?:referencyjny(?: sprawy)?|postępowania|BZP)\s*:",
                            koniec_wiersza, re.I)
    if koniec_wiersza in {"", ".", ",", ";"} or kolejne_pole:
        return FORMATTERS["ted"](numery[0][0])
    return None


_PIERWSZY_ZARZUT = re.compile(r"^[ \t]*Zarzut\s+(?:nr\.?\s+)?1\b[ \t]*[–—:-]?[ \t]*", re.I | re.M)
_PIERWSZA_CZYNNOSC = re.compile(
    r"\b(?:czynności(?:\s+i\s+zaniechań)?|zaniechań(?:\s+i\s+czynności)?)\s+Zamawiającego,?\s+"
    r"polegając(?:ych|ej|e)\s+na\s*:\s*1[.)]\s*", re.I,
)
_OPISY_CZYNNOSCI = {
    1: "Decyzja o odrzuceniu oferty",
    2: "Ogłoszenie wyboru oferty",
    3: "Decyzja o wykluczeniu wykonawcy",
    4: "Publikacja specyfikacji warunków zamówienia (SWZ)",
    5: "Modyfikacja treści SWZ",
    6: "Odpowiedzi/wyjaśnienia do SWZ",
    7: "Zaniechanie odrzucenia oferty",
    8: "Zaniechanie wykluczenia wykonawcy",
    9: "Decyzja o unieważnieniu postępowania",
    10: "Zaniechanie unieważnienia postępowania",
    11: "Opis przedmiotu zamówienia (OPZ)",
    12: "Projektowane postanowienia umowy",
}
_PRZEDMIOT_ODWOLANIA = {
    1: r"czynności (?:zamawiającego polegającej na odrzuceniu|odrzucenia) oferty",
    2: r"czynności wyboru (?:jako )?najkorzystniejszej oferty",
    3: r"czynności wykluczenia (?:odwołującego|wykonawcy) z postępowania",
    4: r"treści (?:specyfikacji warunków zamówienia|SWZ)",
    5: r"modyfikacji treści SWZ",
    6: r"treści wyjaśnień SWZ",
    7: r"zaniechania odrzucenia oferty",
    8: r"zaniechania wykluczenia wykonawcy",
    9: r"czynności unieważnienia postępowania",
    10: r"zaniechania unieważnienia postępowania",
    11: r"postanowień opisu przedmiotu zamówienia",
    12: r"projektowanych postanowień umowy",
}
_DATA_CZYNNOSCI_W_PUNKCIE = re.compile(
    r"\b(?:poinformował(?: wykonawców)?|poinformowany|zawiadomił|powziął wiadomość|"
    r"udzielonych przez zamawiającego|opublikowan(?:ej|ego|ych)(?: przez\.? zamawiającego "
    rf"na stronie internetowej prowadzonego postępowania)?) (?:w dniu|pismem z) ({_DATA})(?: r\.?| roku)?[. ]*$", re.I
)
_KILKA_PRZEDMIOTOW = re.compile(
    r"\b(?:lub|albo|ewentualnie|zamiast)\b|\b(?:i|oraz)\s+(?:czynności|zaniechania|treści|modyfikacji|"
    r"odrzucenia|wyboru|wykluczenia|unieważnienia)\b", re.I,
)


def _pierwszy_przedmiot_odwolania(tekst):
    # W petitum wskazano przedmioty odwołania. Dalej są odrębne, numerowane listy naruszeń i żądań.
    wstep = list(re.finditer(r"\bwnoszę\s+odwołanie\s+wobec\s*:", tekst, re.I))
    if len(wstep) != 1 or re.search(r"\bnie\s*$", tekst[:wstep[0].start()], re.I):
        return None
    if re.search(r"(?im)^[ \t]*(?:załącznik|wzór|przykład|cytat|uzasadnienie)\b", tekst[:wstep[0].start()]):
        return None
    lista = tekst[wstep[0].end():]
    drugi = re.search(r"(?m)^[ \t]*2[.)]\s+", lista)
    if not drugi:
        return None
    poczatek = lista[:drugi.start()]
    # Tesseract może odczytać cyfrę 1 jako pionową kreskę lub literę l.
    punkt = re.fullmatch(
        r"(?s)(.{0,500}?)(?m:^[ \t]*[1Il|][.)][ \t]+)([^;:]{1,650})[;:][\W_]*(?:i[\W_]+)?", poczatek,
    )
    if not punkt or re.search(r"(?m)^[ \t]*[1-9][.)]\s|;", punkt[1]):
        return None
    tresc = " ".join(punkt[2].split())
    if _KILKA_PRZEDMIOTOW.search(tresc):
        return None
    for kod, wzorzec in _PRZEDMIOT_ODWOLANIA.items():
        if re.match(wzorzec + r"\b", tresc, re.I):
            data = _DATA_CZYNNOSCI_W_PUNKCIE.search(tresc)
            dzien = None
            if data and len(_DATA_W_TRESCI.findall(tresc)) == 1:
                kandydat = FORMATTERS["date-iso"](data[1])
                try:
                    dzien = date.fromisoformat(kandydat).isoformat()
                except ValueError:
                    pass
            return kod, _OPISY_CZYNNOSCI[kod], dzien
    return None


_NAZWY_CZYNNOSCI = {
    1: r"odrzuceni[aeu] oferty",
    3: r"wykluczeni[aeu] (?:wykonawcy|odwołującego|z postępowania)",
    5: r"modyfikacj[aię] treści (?:SWZ|specyfikacji warunków zamówienia)",
    7: r"zaniechani[aeu] odrzucenia oferty",
    8: r"zaniechani[aeu] wykluczenia (?:wykonawcy|odwołującego|z postępowania)",
    9: r"unieważnieni[aeu] postępowania",
    10: r"zaniechani[aeu] unieważnienia postępowania",
}
_CZYJA_OFERTA = r"(?: (?:odwołującego|wykonawcy|złożon(?:ej|ą) przez (?:odwołującego|wykonawcę)))?"
_KOGO_WYKLUCZONO = (
    r"(?: z postępowania)? (?:odwołującego|wykonawc[ęy]|podmiot(?:u działającego| działający) wspólnie z odwołującym)"
)
_SWZ = r"(?:SWZ|specyfikacj[ęi] warunków zamówienia)"
_DZIALANIA = {
    1: rf"(?:odrzucił ofertę|poinformował o odrzuceniu oferty){_CZYJA_OFERTA}",
    2: r"ogłosił wybór (?:najkorzystniejszej )?oferty(?: w postępowaniu(?: prowadzonym na podstawie przepisów ustawy)?)?",
    3: rf"(?:wykluczył|poinformował o wykluczeniu){_KOGO_WYKLUCZONO}",
    4: rf"opublikował {_SWZ}",
    5: rf"zmodyfikował treść {_SWZ}",
    6: rf"przekazał wykonawcom odpowiedzi i wyjaśnienia do (?:treści )?{_SWZ}",
    7: rf"nie odrzucił oferty{_CZYJA_OFERTA}",
    8: rf"nie wykluczył{_KOGO_WYKLUCZONO}",
    9: r"unieważni{1,2}ł postępowanie",
    10: r"(?:zaniechał unieważnienia|nie unieważnił) postępowania",
    11: r"udostępnił (?:opis przedmiotu zamówienia|OPZ)",
}
_NARUSZENIE = re.compile(
    r"(?:naruszenia (?:zasady|obowiązku)\b|nieopisania parametrów\b|błędnej oceny ofert\b|"
    r"zaniechania wezwania do wyjaśnień\b)", re.I,
)
_PRZEDMIOT_W_TYTULE = re.compile(
    r"\b(?:odrzuc\w*|wyklucz\w*|unieważni\w*|wyb[oó]r\w*|publikacj\w*|modyfikacj\w*|"
    r"zmian\w*|SWZ|OPZ|opis\w* przedmiotu zamówienia|postanowi\w* umow\w*)\b", re.I,
)
_OSOBNE_WSKAZANIE_CZYNNOSCI = re.compile(
    r"\b(?:zaskarża(?:m|my)?|kwestionuj(?:e|ę|emy)|zarzuca(?:m|my)?|"
    r"(?:przedmiotem|podstawą) (?:tego |pierwszego |niniejszego )?(?:zarzutu|odwołania)|"
    r"(?:zarzut|odwołanie) (?:dotyczy|odnosi się)|w zakresie (?:czynności|zaniechania)|"
    r"(?:naruszenie|uchybienie) polega\w* na|"
    r"(?:odrzucił|odrzucono|wykluczył|wykluczono|unieważni{1,2}ł|unieważniono|"
    r"opublikował|zmodyfikował|ogłosił wybór|zaniechał unieważnienia))\b",
    re.I,
)


def _kategoria_czynnosci(fraza):
    fraza = " ".join(fraza.split())
    if re.search(r"[,;:]|\b(?:i|lub|albo|oraz|bądź|ewentualnie|lecz|zamiast|także|również|nie)\b", fraza, re.I):
        return None
    fraza = re.sub(r"^(?:bezpodstawn\w+|bezzasadn\w+|wadliw\w+|niezgodn\w+ z prawem) ", "", fraza, flags=re.I)
    for kod, wzorzec in _NAZWY_CZYNNOSCI.items():
        dopasowanie = re.match(wzorzec + r"\b", fraza, re.I)
        if dopasowanie and not re.search(
            r"\b(?:zaniechani|odrzuceni|wykluczeni|unieważnieni|modyfikacj|wybor|publikacj)\w*",
            fraza[dopasowanie.end():], re.I,
        ):
            return kod, _OPISY_CZYNNOSCI[kod]
    return None


def _czynnosc_przed_zarzutem(tekst):
    deklaracja = _deklaracja_przed_zarzutem(tekst)
    if not deklaracja:
        return None
    fraza, dzien, tytul, uzasadnienie = deklaracja
    kod = next((kod for kod, wzorzec in _DZIALANIA.items() if re.fullmatch(wzorzec, fraza, re.I)), None)
    if kod is None or _OSOBNE_WSKAZANIE_CZYNNOSCI.search(" ".join(uzasadnienie.split())):
        return None
    # Tytuł może podawać zarzucane naruszenie, a poprzedzające zdanie samą czynność.
    # Jawne wskazanie innego rozstrzygnięcia w pierwszym zarzucie wyklucza tę interpretację.
    kategoria = _kategoria_czynnosci(tytul)
    if kategoria:
        if kategoria[0] != kod:
            return None
    elif not _NARUSZENIE.match(tytul) or _PRZEDMIOT_W_TYTULE.search(tytul):
        return None
    return kod, _OPISY_CZYNNOSCI[kod], dzien


def _pierwszy_zarzut(tekst, dane, deklaracja):
    if not isinstance(dane, dict) or not {"czynnosc_powod_id", "czynnosc_opis"} <= dane.keys():
        return
    if deklaracja:
        dane["czynnosc_powod_id"], dane["czynnosc_opis"] = deklaracja[:2]
        return
    zarzuty = list(_PIERWSZY_ZARZUT.finditer(tekst))
    if len(zarzuty) != 1:
        return
    przed = tekst[:zarzuty[0].start()]
    listy = list(_PIERWSZA_CZYNNOSC.finditer(przed))
    if len(listy) != 1:
        return
    # Żądanie i zarzut osobno nazywają zaskarżoną czynność. Zachowaj wynik modelu, gdy się różnią.
    punkt = re.match(r"([^;]+?)(?:;|\n[ \t]*2[.)])", przed[listy[0].end():], re.S)
    naglowek = re.match(r"(.+?)(?:,\s*tj\.|[:;]|[ \t]*\n[ \t]*Zarzut\b)", tekst[zarzuty[0].end():], re.I | re.S)
    if punkt and naglowek:
        kategoria = _kategoria_czynnosci(naglowek[1])
        if kategoria and kategoria == _kategoria_czynnosci(punkt[1]):
            dane["czynnosc_powod_id"], dane["czynnosc_opis"] = kategoria


class odwolanie:
    @staticmethod
    def zastosuj(tekst: str, wynik: dict) -> None:
        deklaracja = _pierwszy_przedmiot_odwolania(tekst) or _czynnosc_przed_zarzutem(tekst)
        _pierwszy_zarzut(tekst, wynik.get("OdwolanieKIO"), deklaracja)
        naglowek = _naglowek(tekst)
        tekst_naglowka = "\n".join(naglowek)
        _rozdziel_pelnomocnikow(tekst_naglowka, tekst, wynik.get("Odwolujacy"))
        _mail_pelnomocnika_z_ocr(tekst_naglowka, tekst, wynik.get("Odwolujacy"))
        odwolanie_kio = wynik.get("OdwolanieKIO")
        if isinstance(odwolanie_kio, dict):
            datowniki = set()
            for numer, wiersz in enumerate(naglowek):
                datownik = _WIERSZ_DATY.fullmatch(wiersz)
                if datownik and (numer == 0 or datownik["miejsce"] or datownik["etykieta"]):
                    sformatowana = FORMATTERS["date-iso"](datownik["data"])
                    try:
                        data = date.fromisoformat(sformatowana)
                    except ValueError:
                        continue
                    datowniki.add((data.isoformat(), datownik["miejsce"]))
            if len(datowniki) == 1:
                data_pisma, miejsce = datowniki.pop()
                _wpisz(odwolanie_kio, "data", data_pisma)
                _wpisz(odwolanie_kio, "miejscowosc", miejsce)
            _daty_czynnosci_i_pisma(tekst, naglowek, odwolanie_kio, deklaracja)

        zamowienie = wynik.get("ZamowieniePubliczne")
        if isinstance(zamowienie, dict):
            tytuly = {
                dopasowanie["tytul"].strip()
                for dopasowanie in _TYTUL.finditer(" ".join(naglowek))
                if QUOTE_PAIRS[dopasowanie["otwarcie"]] == dopasowanie["zamkniecie"]
                and dopasowanie["tytul"].strip()
            }
            if len(tytuly) == 1:
                _wpisz(zamowienie, "tytul", tytuly.pop())
            _wpisz(zamowienie, "numer_ted", _numer_ted(tekst_naglowka))

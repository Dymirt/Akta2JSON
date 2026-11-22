"""Pomiar lokalnych reguł na PDF-ach i etykietach z publicznego zestawu UZP."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from anon_legal_pl.ocr import pdf_na_tekst

from odwolania.cli import find_pdfs
from odwolania.extraction import format_result
from odwolania.rules import empty_result
from odwolania.templates import TemplateRegistry


KLASY = ("odwolanie", "pelnomocnictwo", "przelew")
SKANY = {"odwolania": "odwolanie", "pelnomocnictwa": "pelnomocnictwo", "potwierdzenia": "przelew"}
SKAN = Path("szablon-aplikacja/input/case1/przyklad odwolanie.pdf")
# Minimalne pokrycie zaobserwowane dla poszczególnych pól w referencyjnym przebiegu 60 spraw.
MINIMUM = {
    "odwolanie": {
        "OdwolanieKIO.data": 45, "OdwolanieKIO.miejscowosc": 45,
        "OdwolanieKIO.czynnosc_powod_id": 48, "OdwolanieKIO.czynnosc_opis": 48,
        "OdwolanieKIO.czynnosc_dzien": 54,
        "ZamowieniePubliczne.tytul": 60, "ZamowieniePubliczne.numer_ted": 47,
    },
    "pelnomocnictwo": {"mocodawca[].data.krs": 20, "mocodawca[].data.nip": 20, "mocodawca[].data.typ": 11},
    "przelew": {
        "przelew_bankowy.data_operacji": 55, "przelew_bankowy.kwota": 49,
        "przelew_bankowy.na_rachunek": 49, "przelew_bankowy.z_rachunku": 49,
        "przelew_bankowy.numer_transakcji": 60, "przelew_bankowy.tytul": 57,
    },
}


def pola(wartosc, sciezka=()):
    if isinstance(wartosc, dict):
        for klucz, element in wartosc.items():
            yield from pola(element, (*sciezka, klucz))
    elif isinstance(wartosc, list):
        for indeks, element in enumerate(wartosc):
            yield from pola(element, (*sciezka, indeks))
    else:
        yield sciezka, wartosc


def nazwa_pola(sciezka):
    return ".".join("[]" if isinstance(klucz, int) else klucz for klucz in sciezka).replace(".[]", "[]")


def odczytaj_json(sciezka):
    return json.loads(sciezka.read_text(encoding="utf-8"))


def brak_pl_w_etykiecie(pole, wynik, etykieta, tekst):
    if pole not in {("przelew_bankowy", "z_rachunku"), ("przelew_bankowy", "na_rachunek")}:
        return False
    if not isinstance(etykieta, str) or not re.fullmatch(r"[0-9]{26}", etykieta) or wynik != "PL" + etykieta:
        return False
    wzorzec = r"(?<!\w)PL\s*" + r"\s*".join(etykieta) + r"(?!\d)"
    return bool(re.search(wzorzec, tekst, re.I))


def wynik_poczatkowy(wzorzec, archiwalny_json):
    wynik = empty_result(wzorzec.shape)
    if wzorzec.name == "pelnomocnictwo" and archiwalny_json is not None:
        for rekord in odczytaj_json(archiwalny_json)["mocodawca"]:
            mocodawca = empty_result(wzorzec.shape["mocodawca"][0])
            mocodawca["data"]["nazwa"] = rekord["data"]["nazwa"]
            wynik["mocodawca"].append(mocodawca)
    return wynik


def referencja(sciezka):
    """Układ publicznych etykiet UZP. Rozpoznawanie w aplikacji dostaje wyłącznie tekst."""
    if sciezka == SKAN:
        return "skan-szablon", "odwolanie", None
    if sciezka.parts[:2] == ("dane", "skany"):
        klasa = SKANY[sciezka.parts[2]]
        return f"skany/{klasa}", klasa, sciezka.with_suffix(".json")
    if sciezka.parts[0] == "dane" and sciezka.parent.name.startswith("przyklad_"):
        klasa = "przelew" if sciezka.stem == "potwierdzenie_przelewu" else sciezka.stem
        if klasa in KLASY:
            return klasa, klasa, sciezka.with_name(klasa + ".json")
    return "negatywne", None, None


def pomiar(materialy, archiwum, wzorce):
    rejestr = TemplateRegistry.load(wzorce)
    dane = materialy / "dane"
    wykryte = Counter()
    oczekiwane = Counter()
    sprawy = defaultdict(set)
    aktywacje, trafienia, dostepne = Counter(), Counter(), Counter()
    bledy = []
    rozbieznosci_skanow = []
    pominiete_prefiksy = 0

    for pdf in find_pdfs(dane) + find_pdfs(materialy / "szablon-aplikacja/input"):
        sciezka = pdf.relative_to(materialy)
        grupa, klasa, plik_etykiety = referencja(sciezka)
        oczekiwane[grupa] += 1
        if grupa in KLASY:
            sprawy[klasa].add(pdf.parent.relative_to(dane))
        tekst = pdf_na_tekst(pdf)
        wzorzec = rejestr.classify(tekst)
        # Etykieta jest używana wyłącznie do oceny; błędna klasyfikacja też obniża czułość.
        etykieta = dict(pola(odczytaj_json(materialy / plik_etykiety))) if plik_etykiety else {}
        for pole, wartosc in etykieta.items():
            if wartosc is not None:
                dostepne[grupa, nazwa_pola(pole)] += 1
        if (wzorzec.name if wzorzec else None) != klasa:
            bledy.append(f"{sciezka}: błędna klasyfikacja")
            continue
        wykryte[grupa] += 1
        if plik_etykiety is None:
            continue
        if wzorzec.rule is None:
            raise ValueError(f"Brak reguły typu {klasa}")

        baza = archiwum / pdf.relative_to(dane).with_suffix(".json") if archiwum and grupa in KLASY else None
        wynik = wynik_poczatkowy(wzorzec, baza)
        poczatkowe = dict(pola(format_result(wynik, wzorzec.formatters)))
        wzorzec.apply_rules(tekst, wynik)
        wynik = format_result(wynik, wzorzec.formatters)
        for pole, wartosc in pola(wynik):
            if wartosc is None or wartosc == poczatkowe.get(pole):
                continue
            klucz = grupa, nazwa_pola(pole)
            aktywacje[klucz] += 1
            ref = etykieta.get(pole)
            liczby = type(ref) in (int, float) and type(wartosc) in (int, float)
            if wartosc == ref and (liczby or type(wartosc) is type(ref)):
                trafienia[klucz] += 1
            elif brak_pl_w_etykiecie(pole, wartosc, ref, tekst):
                # Zachowaj ścisłą metrykę etykiet, ale nie zgłaszaj poprawnego prefiksu z PDF jako regresji.
                pominiete_prefiksy += 1
            else:
                rozbieznosci = bledy if grupa in KLASY else rozbieznosci_skanow
                rozbieznosci.append(f"{sciezka}: niezgodne pole {'.'.join(map(str, pole))}")

    pelny_zestaw = {Path(f"przyklad_{nr:02}") for nr in range(1, 61)}
    for klasa in KLASY:
        if sprawy[klasa] != pelny_zestaw:
            bledy.append(f"{klasa}: niepełny zbiór 60 spraw")
    wymagane = {**dict.fromkeys(KLASY, 60), **{f"skany/{klasa}": 10 for klasa in KLASY},
                "negatywne": 17, "skan-szablon": 1}
    if oczekiwane != wymagane:
        bledy.append(f"Inwentarz PDF różni się od zestawu UZP: {dict(oczekiwane)}")

    for klasa, minima in MINIMUM.items():
        if klasa == "pelnomocnictwo" and archiwum is None:
            continue  # Progi historyczne dotyczą reguł uruchamianych po identyfikacji mocodawców przez AI.
        for pole, minimum in minima.items():
            klucz = klasa, pole
            aktywacje.setdefault(klucz, 0)
            if aktywacje[klucz] < minimum:
                blad = f"{klasa}.{pole}: {aktywacje[klucz]} aktywacji, wymagane co najmniej {minimum}."
                if klasa == "pelnomocnictwo":
                    blad += " Pokrycie zależy także od nazw i liczby mocodawców w podanym archiwum AI."
                bledy.append(blad)

    print("Klasyfikacja (poprawne / dokumenty)")
    for klasa in wymagane:
        print(f"  {klasa}: {wykryte[klasa]}/{oczekiwane[klasa]}")
    print("Pole | aktywacje | trafienia | niepuste wartości w etykietach")
    for klucz in sorted(aktywacje):
        print(" | ".join(map(str, (".".join(klucz), aktywacje[klucz], trafienia[klucz], dostepne[klucz]))))
    print(f"Łącznie {sum(trafienia.values())}/{sum(aktywacje.values())} poprawnych aktywacji.")
    print(f"Rachunki zgodne z PDF-em z prefiksem PL pominiętym w etykiecie: {pominiete_prefiksy}.")
    print("Samodzielne reguły na skanach (mikro, dokładna zgodność wartości i ścieżki)")
    for klasa in KLASY:
        grupa = f"skany/{klasa}"
        correct, predicted, expected = (
            sum(v for (g, _), v in counts.items() if g == grupa) for counts in (trafienia, aktywacje, dostepne)
        )
        precision = correct / predicted if predicted else 0
        recall = correct / expected if expected else 0
        f1 = 2 * correct / (predicted + expected) if predicted + expected else 0
        print(f"  {grupa}: P={precision:.2%} R={recall:.2%} F1={f1:.2%}")
    for blad in rozbieznosci_skanow:
        print(blad)
    for blad in bledy:
        print(blad)
    return int(bool(bledy))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materialy", type=Path, help="repozytorium UZP z dane/ i szablon-aplikacja/")
    parser.add_argument("archiwum", type=Path, nargs="?", help="opcjonalny katalog z wynikami AI przyklad_XX/pelnomocnictwo.json")
    parser.add_argument("wzorce", type=Path, help="katalog wzorców jsonc i klas reguł")
    args = parser.parse_args()
    raise SystemExit(pomiar(args.materialy, args.archiwum, args.wzorce))

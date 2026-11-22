import unittest
from copy import deepcopy
from pathlib import Path

from odwolania.templates import DocumentTemplate


class AppealRulesTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "oczekiwane-json" / "odwolanie.jsonc"
        self.rule = DocumentTemplate.load(path).rule
        self.result = {
            "OdwolanieKIO": {"data": None, "miejscowosc": None},
            "ZamowieniePubliczne": {"tytul": "Tytuł z ekstrakcji"},
        }

    def test_ocr_email_separator_requires_named_counsel_and_literal_domain(self):
        osoba = {"imie_nazwisko": "Żaneta Łukasik", "mail": None}
        self.result["Odwolujacy"] = [{"pelnomocnik": osoba}]
        poczatek = "Odwołujący: Firma A\nradca prawny Żaneta Łukasik\ne-mail: "
        for separator in ("Q", "©", "(OQ", "(a "):
            with self.subTest(separator=separator):
                osoba["mail"] = None
                self.rule(poczatek + "z.lukasik" + separator + "firma.pl", self.result)
                self.assertEqual(osoba["mail"], "z.lukasik@firma.pl")
        osoba["mail"] = None
        self.rule(poczatek + "z.lukasikafirma.pl\nwww.firma.pl", self.result)
        self.assertEqual(osoba["mail"], "z.lukasik@firma.pl")
        osoba["mail"] = "inna@firma.pl"
        self.rule(poczatek + "z.lukasikQfirma.pl", self.result)
        self.assertEqual(osoba["mail"], "inna@firma.pl")

    def test_ocr_email_preserves_missing_or_ambiguous_address(self):
        osoba = {"imie_nazwisko": "Adam Wrona", "mail": None}
        self.result["Odwolujacy"] = [{"pelnomocnik": osoba}]
        naglowek = "Odwołujący: Firma A\nadw. Adam Wrona\n"
        for opis in (
            "e-mail: a.wronafirma.pl",
            "e-mail: a.wronaafirma.pl\nwww.firma.pl.info",
            "e-mail: a.wronaQfirma.exa ple",
            "e-mail: a.wronaQfirma.pl\ne-mail: a.wronaQdruga.pl",
            "e-mail: a.wronaQfirma.pl\ne-mail: sekretariat@firma.pl",
            "e-mail: kontaktQfirma.pl",
            "Zamawiający: Firma B\ne-mail: a.wronaQfirma.pl",
        ):
            with self.subTest(opis=opis):
                self.rule(naglowek + opis, self.result)
                self.assertIsNone(osoba["mail"])
        self.rule(naglowek.replace("adw.", "dyrektor") + "e-mail: a.wronaQfirma.pl", self.result)
        self.assertIsNone(osoba["mail"])

    def test_reads_header_and_ignores_later_evidence(self):
        text = (
            "Nowy Sącz, dnia 3 maja 2026 roku\n"
            "Dotyczy zamówienia pod nazwą „Odbiór\ni transport odpadów”, nr referencyjny X/1.\n"
            "Uzasadnienie\n"
            "Warszawa, 04.05.2026\n"
            "Wartość zamówienia pn. „Inny tytuł”, nr referencyjny X/2."
        )
        self.rule(text, self.result)
        self.assertEqual(self.result["OdwolanieKIO"], {"data": "2026-05-03", "miejscowosc": "Nowy Sącz"})
        self.assertEqual(self.result["ZamowieniePubliczne"]["tytul"], "Odbiór i transport odpadów")

    def test_preserves_extraction_if_evidence_is_missing_invalid_or_ambiguous(self):
        self.result["OdwolanieKIO"] = {"data": "2026-01-02", "miejscowosc": "Opole"}
        expected = deepcopy(self.result)
        for text in (
            "ODWOŁANIE\nPrezes Krajowej Izby Odwoławczej",
            "Kraków, 31.02.2026",
            "Gdańsk, 10.02.2026\nKielce, 11.02.2026",
            'Dotyczy zamówienia pn. „Usługa A”, nr referencyjny A/1.\n'
            'Dotyczy zamówienia pn. "Usługa B"; nr referencyjny B/1.',
        ):
            with self.subTest(text=text):
                self.rule(text, self.result)
                self.assertEqual(self.result, expected)

    def test_ted_requires_a_single_label_and_number_in_the_procurement_header(self):
        subject = "Dotyczy: postępowania o udzielenie zamówienia publicznego, "
        self.result["ZamowieniePubliczne"]["numer_ted"] = None
        self.rule(subject + "ogłoszenie w Dzienniku Urzędowym Unii\nEuropejskiej nr 2026/S\n101-123456", self.result)
        self.assertEqual(self.result["ZamowieniePubliczne"]["numer_ted"], "123456-2026")
        for text in (
            subject + "123456-2026",
            subject + "TED: 123456-2026, 543210-2026",
            subject + "TED: 123456-2026, TED: nieczytelny",
            "Dotyczy: innej sprawy, TED: 123456-2026",
            subject + "nr referencyjny P/1\nUzasadnienie\nTED: 123456-2026",
            subject + "nr referencyjny P/1\nZamawiający:\nPoprzednie ogłoszenie TED: 123456-2026",
        ):
            with self.subTest(text=text):
                self.result["ZamowieniePubliczne"]["numer_ted"] = "z ekstrakcji"
                self.rule(text, self.result)
                self.assertEqual(self.result["ZamowieniePubliczne"]["numer_ted"], "z ekstrakcji")

    def test_ted_in_its_own_field_belongs_to_the_current_procedure(self):
        subject = "Dotyczy: postępowania o udzielenie zamówienia publicznego"
        pole = self.result["ZamowieniePubliczne"]
        for tail in ("\nTED: 123456-2026", ", TED: 123456-2026, nr postępowania: ABC/26"):
            with self.subTest(tail=tail):
                pole["numer_ted"] = None
                self.rule(subject + tail, self.result)
                self.assertEqual(pole["numer_ted"], "123456-2026")
        for tail in (
            ", informacyjnie podano stary numer TED: 123456-2026",
            "\nPoprzednie postępowanie\nTED: 123456-2026",
            "\nOgłoszenie historyczne\nTED: 123456-2026",
            "\nTED: 123456-2026\n(numer poprzedniego ogłoszenia)",
            ", TED: 123456-2026 (dla innego postępowania)",
            ", TED: 123456-2026.01",
            ", BZP: 123456-2026",
            ", TED: 123456-2026\nTED nieczytelny",
            ", nr referencyjny X/26\fTED: 123456-2026",
        ):
            with self.subTest(tail=tail):
                pole["numer_ted"] = "z ekstrakcji"
                self.rule(subject + tail, self.result)
                self.assertEqual(pole["numer_ted"], "z ekstrakcji")

    def test_representative_requires_unambiguous_party_and_contact_designation(self):
        source = (
            "Odwołujący:\nFirma A\nreprezentowana przez: r. pr. Joanna Nowak, adw. Jan Nowicki\n"
            "adres do korespondencji: kancelaria\n"
        )
        merged = "Joanna Nowak Jan Nowicki"
        osoba = {"imie_nazwisko": merged}
        self.result["Odwolujacy"] = [{"pelnomocnik": osoba}]
        for text, expected in (
            (source + "Osoba do kontaktu: adw. Jan Nowicki", "Jan Nowicki"),
            (source.replace("adres do korespondencji:", "Osoba do doręczeń: Jan Nowicki\nadres do korespondencji:"), "Jan Nowicki"),
            (source + "Osoba do kontaktu: ul. Krótka 2", merged),
            (source + "Osoba do kontaktu: Jan Nowicki\nOsoba do doręczeń: Joanna Nowak", merged),
            (source + "Zamawiający:\nOsoba do kontaktu: Jan Nowicki", merged),
            (source + "\fKorespondencję prosimy kierować do adw. Jana Nowickiego.", merged),
            (source + "\fOdwołujący nr 2:\nFirma B", merged),
            (source.replace("kancelaria", "adw. Jan Nowicki, ul. Krótka 2"), merged),
            (source.replace("reprezentowana", "Przystępujący:\nFirma B\nreprezentowana"), merged),
        ):
            with self.subTest(text=text):
                osoba["imie_nazwisko"] = merged
                self.rule(text, self.result)
                self.assertEqual(osoba["imie_nazwisko"], expected)
        self.result["Odwolujacy"].append({"pelnomocnik": {"imie_nazwisko": merged}})
        przed = deepcopy(self.result)
        self.rule(source, self.result)
        self.assertEqual(self.result, przed)

    def test_scanned_list_of_named_counsel_uses_order_or_explicit_contact(self):
        poczatek = ("Odwołujący: Firma A\nreprezentowany przez pełnomocnika:\n"
                    "adwokat Anna Lis\nradca prawny Maria Kruk\nadres do korespondencji: kancelaria\n")
        osoba = {"imie_nazwisko": None}
        self.result["Odwolujacy"] = [{"pelnomocnik": osoba}]
        for dotychczasowa, dopisek, oczekiwana in (
            (None, "", "Anna Lis"),
            ("Anna Lis Maria Kruk", "", "Anna Lis"),
            ("Anna Lis", "Osoba do kontaktu: r. pr. Maria Kruk", "Maria Kruk"),
            (None, "Osoba do kontaktu: inny prawnik", None),
        ):
            with self.subTest(dotychczasowa=dotychczasowa, dopisek=dopisek):
                osoba["imie_nazwisko"] = dotychczasowa
                self.rule(poczatek + dopisek, self.result)
                self.assertEqual(osoba["imie_nazwisko"], oczekiwana)

    def test_empty_party_list_requires_independent_confirmation_of_the_appellant(self):
        naglowek = ("Odwołujący: Firma A sp. k.\nreprezentowany przez pełnomocnika:\n"
                    "radca prawny Anna Lis\nadw. Maria Kruk\nKancelaria Radcy Prawnego Anna Lis\n")
        self.result["Odwolujacy"] = []
        self.rule(naglowek, self.result)
        self.assertEqual(self.result["Odwolujacy"], [])
        self.rule(naglowek + "Działając w imieniu Odwołującego — Firma A sp. k. (dalej: „Odwołujący”)", self.result)
        strona, = self.result["Odwolujacy"]
        self.assertEqual(strona["nazwa"], "Firma A sp. k.")
        self.assertEqual(strona["pelnomocnik"]["imie_nazwisko"], "Anna Lis")

    def test_splits_only_a_concatenated_list_in_the_appellants_own_section(self):
        text = (
            "Odwołujący:\nFirma A\nreprezentowana przez: r. pr. Joanna Nowak, adw. Jan Nowicki\n"
            "adres do korespondencji: kancelaria\nDotyczy: postępowania"
        )
        osoba = {"imie_nazwisko": "Joanna Nowak Jan Nowicki"}
        self.result["Odwolujacy"] = [{"pelnomocnik": osoba}]
        self.rule(text, self.result)
        self.assertEqual(osoba["imie_nazwisko"], "Joanna Nowak")
        for source, current in (
            (text, "Jan Nowicki"),
            (text + "\nOsoba do kontaktu: Jan Nowicki", "Joanna Nowak Jan Nowicki"),
            (text.replace("Odwołujący:", "Zamawiający:"), "Joanna Nowak Jan Nowicki"),
            (text, None),
        ):
            with self.subTest(source=source, current=current):
                osoba["imie_nazwisko"] = current
                self.rule(source, self.result)
                self.assertEqual(osoba["imie_nazwisko"], current)

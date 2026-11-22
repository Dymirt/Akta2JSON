import re
import unittest
from importlib.util import find_spec

from odwolania.cli import local_pdf_processor


@unittest.skipUnless(find_spec("pl_core_news_md"), "Test wymaga polskiego modelu z obrazu Docker")
class MaskowanieMailiOCR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maskuj = staticmethod(local_pdf_processor().pseudonymize)

    def sprawdz_mape(self, zrodlo):
        tekst, mapa = self.maskuj(zrodlo)
        odtworzony = re.sub(r"\[[A-Z_]+_\d+\]", lambda m: mapa[m[0]], tekst)
        self.assertEqual(odtworzony, zrodlo)
        return tekst, mapa

    def test_powtorzenie_uszkodzonego_maila_poza_etykieta(self):
        for mail in ("z.olszewska Qsikora-kancelaria.exam le i", "r.malinowski(a cieslak-kancelaria.example"):
            with self.subTest(mail=mail):
                tekst, _ = self.sprawdz_mape(f"e-mail: {mail}\n\nKopia: {mail}")
                pierwszy, kopia = tekst.split("\n\n")
                self.assertRegex(pierwszy, r"^e-mail: \[EMAIL_\d+\]")
                self.assertEqual(pierwszy.removeprefix("e-mail: "), kopia.removeprefix("Kopia: "))
                for fragment in (mail.split()[0], "-kancelaria."):
                    self.assertNotIn(fragment, tekst)

    def test_zachowuje_poprawny_mail_komentarz_i_odrebna_etykiete(self):
        tekst, mapa = self.sprawdz_mape(
            "e-mail: j.nowakQfirma.pl, tylko w dni robocze\n"
            "e-mail: kontakt@example.org, tel. +48 58 123 45 67"
        )
        self.assertRegex(tekst, r"e-mail: \[EMAIL_\d+\], tylko w dni robocze")
        self.assertRegex(tekst, r"e-mail: \[EMAIL_\d+\], tel\. \[TELEFON_\d+\]")
        self.assertIn("j.nowakQfirma.pl", mapa.values())
        self.assertIn("kontakt@example.org", mapa.values())

    def test_opis_po_etykiecie_nie_staje_sie_adresem(self):
        tresc = "mail: tak\nmail: proszę pisać do sekretariatu\ne-mail: X\nOdpowiedź X: tak."
        tekst, mapa = self.sprawdz_mape(tresc)
        self.assertNotIn("[EMAIL_", tekst)
        self.assertFalse(any(tag.startswith("[EMAIL_") for tag in mapa))

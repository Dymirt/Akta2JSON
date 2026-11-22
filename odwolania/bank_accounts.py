"""National IBAN patterns shared by PDF extraction and pseudonymization."""

import re


# National BBAN structures, with adjacent runs of the same kind combined.
# Source: Swift IBAN Registry, release 103, https://www.swift.com/swift-resource/9606/download
# n = digits, a = letters, c = alphanumeric. Polish NRB/IBAN rules also cover UZP's 24-digit format.
_BBAN_FORMATS = {
    "AD": "8n 12c",
    "AE IL SO TL": "19n",
    "AL CY": "8n 16c",
    "AT BA EE LT MN XK": "16n",
    "AZ": "4a 20c",
    "BE": "12n",
    "BG": "4a 6n 8c",
    "BH": "4a 14c",
    "BI DJ MR": "23n",
    "BR": "8c 15n 2c",
    "BY": "4c 4n 16c",
    "CH LI": "5n 12c",
    "CR DE ME RS VA": "18n",
    "CZ ES SE SK TN": "20n",
    "DK FI FO GL SD": "14n",
    "DO": "4c 20n",
    "EG": "25n",
    "FK": "2a 12n",
    "FR MC": "10n 11c 2n",
    "GB IE": "4a 14n",
    "GE": "2a 16n",
    "GI": "4a 15c",
    "GR": "7n 16c",
    "GT": "24c",
    "HN NI SV": "4a 20n",
    "HR": "17n",
    "HU": "24n",
    "IQ": "4a 15n",
    "IS": "22n",
    "IT SM": "1a 10n 12c",
    "JO YE": "4a 4n 18c",
    "KW": "4a 22c",
    "KZ LU": "3n 13c",
    "LB": "4n 20c",
    "LC": "4a 24c",
    "LV": "4a 13c",
    "LY PT ST": "21n",
    "MD": "20c",
    "MK": "3n 10c 2n",
    "MT": "4a 5n 18c",
    "MU": "4a 19n 3a",
    "NL": "4a 10n",
    "NO": "11n",
    "OM": "3n 16c",
    "PK RO": "4a 16c",
    "PS QA": "4a 21c",
    "RU": "14n 15c",
    "SA": "2n 18c",
    "SC": "4a 20n 3a",
    "SI": "15n",
    "TR": "6n 16c",
    "UA": "6n 19c",
    "VG": "4a 16n",
}


def _foreign_iban_pattern() -> re.Pattern[str]:
    symbols = {"n": "[0-9]", "a": "[A-Za-z]", "c": "[A-Za-z0-9]"}
    alternatives = []
    for countries, bban in _BBAN_FORMATS.items():
        country = "|".join(countries.split())
        parts = [rf"(?ai:{country})"]
        for run in ("2n", *bban.split()):
            symbol = symbols[run[-1]]
            length = int(run[:-1])
            parts.append(rf"(?:[^\S\f]*{symbol}){{{length}}}")
        alternatives.append("".join(parts))
    return re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)")


FOREIGN_IBAN = _foreign_iban_pattern()

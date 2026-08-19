"""
testo.py - Normalizzazione di nomi e Id. UNICO punto di verita'.

Prima esistevano due normalize_str diverse (build_master e scout_engine): quella
del motore convertiva 'ø' in 'o', quella dello scout la cancellava. Risultato:
"Hojlund" e "Hjlund", due chiavi diverse per lo stesso giocatore. Ora entrambi
importano da qui.
"""

import re
import unicodedata

# Lettere che la normalizzazione standard NFKD cancella invece di convertire.
LETTERE_SPECIALI = str.maketrans({
    'ø': 'o', 'Ø': 'O', 'đ': 'd', 'Đ': 'D', 'ł': 'l', 'Ł': 'L',
    'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE',
    'ð': 'd', 'þ': 'th',
    'ı': 'i', 'İ': 'I',          # turco: la i senza punto (Yildiz)
    'ħ': 'h', 'ŧ': 't', 'ĸ': 'k',
})


def normalize_str(s):
    """'Højlund M.' -> 'hojlund m'. Vuoto per None/NaN."""
    if s is None:
        return ""
    s = str(s)
    if s.lower() in ('nan', 'nat', 'none'):
        return ""
    s = s.translate(LETTERE_SPECIALI)
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", " ", s).lower()
    return " ".join(s.split())


def clean_id(x):
    """Id come stringa: via BOM, spazi e decimali finti ('4431.0' -> '4431')."""
    s = str(x).replace('\ufeff', '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def parole(nome):
    return normalize_str(nome).split()


def abbreviazione_compatibile(parola_api, parola_listone):
    """
    Il listone Fantacalcio abbrevia il nome proprio: "Pessina Mas.".
    L'API scrive per esteso: "Matteo Pessina".

    Il vecchio confronto guardava SOLO la prima lettera, quindi "Mas." e
    "Matteo" risultavano compatibili e Massimo Pessina (portiere 2007) si
    prendeva le statistiche di Matteo Pessina. Qui si confronta il prefisso
    intero: 'matteo'.startswith('mas') -> False. Corretto.
    """
    if not parola_api or not parola_listone:
        return False
    if len(parola_listone) == 1:          # iniziale secca: "Martinez L."
        return parola_api[0] == parola_listone
    return parola_api.startswith(parola_listone)


def match_nomi_abbreviati(nome_lungo, nome_breve):
    """Stesso cognome + nome proprio compatibile come prefisso."""
    n1, n2 = parole(nome_lungo), parole(nome_breve)
    if not n1 or not n2:
        return False
    if n1[-1] != n2[-1]:
        return False
    if len(n1) == 1 or len(n2) == 1:
        return True
    return abbreviazione_compatibile(n1[0], n2[0])

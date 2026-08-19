"""
build_master.py - Genera Lista_Finale_Master.csv, unica fonte di verita'.

Catena delle fonti:
  1. Quotazioni_Fantacalcio_Stagione_*.xlsx  -> CHI e' in Serie A, in che
     squadra, quanto vale (Qt.A, FVM ufficiale). E' il file piu' recente.
  2. Statistiche.xlsx                        -> come ha reso l'anno scorso.
  3. Lista-FantaAsta-Fantacalcio.csv         -> anagrafica (foto, piede,
     nazionalita', nome completo). Solo arricchimento.
  4. API-Football                            -> rose aggiornate, foto, gare
     saltate, indisponibili di oggi.

Principio: si scrivono FATTI. Il perche' lo decide chi legge.
"""

import os
import re
import sys
import glob
import json
import datetime

import pandas as pd

from scout_engine import ScoutEngine
from testo import normalize_str, clean_id, abbreviazione_compatibile

# ----------------------------------------------------------------------
# PARAMETRI
# ----------------------------------------------------------------------
SQUADRE_LEGA = int(os.getenv("FANTA_SQUADRE_LEGA", "8"))
BUDGET_LEGA = int(os.getenv("FANTA_BUDGET", "500"))
QUOTE_RUOLO = {'P': 0.08, 'D': 0.14, 'C': 0.28, 'A': 0.50}
SLOT_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
ESPONENTE_PREZZO = float(os.getenv("FANTA_ESPONENTE", "1.0"))

# Da dove arriva il valore su cui si calcolano prezzi e fasce:
#   'ufficiale' -> FVM del file quotazioni (default: e' il mercato)
#   'stima'     -> il modello interno
#   'misto'     -> media geometrica dei due
FONTE_FVM = os.getenv("FANTA_FVM", "ufficiale").strip().lower()

K_SHRINK = 8
BASELINE_DEFAULT = {'P': 5.40, 'D': 5.80, 'C': 6.00, 'A': 6.20}
PRESENZE_SOSPETTE = int(os.getenv("FANTA_PRESENZE_SOSPETTE", "26"))

PRESENZE_MINIME_AVVISO = int(os.getenv("FANTA_PRESENZE_AVVISO", "5"))
MAX_VERIFICHE_AVVISO = int(os.getenv("FANTA_MAX_VERIFICHE", "150"))

# Se True, mancanze gravi (niente quotazioni, niente statistiche) fanno fallire
# il run invece di produrre un listone silenziosamente sbagliato.
STRICT = os.getenv("FANTA_STRICT", "1") not in ('0', 'false', 'False', '')

BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta',
             'Lazio', 'Fiorentina', 'Bologna', 'Como']

FILE_MASTER = "Lista_Finale_Master.csv"
FILE_AVVISI = "avvisi.json"
FILE_MESSAGGIO = "avviso.txt"

COLONNE_STATS = ['Pv', 'Mv', 'Fm', 'Gf', 'Gs', 'Rp', 'Rc', 'R+', 'R-', 'Ass', 'Amm', 'Esp']
COLONNE_DECIMALI = {'Mv', 'Fm'}

# Colonne del CSV anagrafica (senza intestazione, ordine fisso)
COLONNE_CSV_BASE = [
    'Id', 'Nome_Breve', 'Nome_Completo', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I',
    'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita',
    'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3',
]

# Ordine finale del Master. FantaBot legge per NOME di colonna, quindi
# aggiungerne non rompe nulla; toglierne si'.
COLONNE_MASTER = [
    'Id', 'Nome', 'Nome_Breve', 'Nome_Completo', 'R', 'Ruolo_Esteso', 'Squadra',
    'Qt.A', 'Qt.I', 'Qt.M', 'Diff.M',
    'FVM', 'FVM.M', 'FVM_Ufficiale', 'FVM_Stima', 'Scarto', 'Prezzo',
    'Piede', 'Nazionalita', 'DataNascita', 'PhotoURL', 'FotoAPI',
    'GareSaltate', 'MotivoStop', 'GareSaltateAltro', 'MotivoAltro',
    'Infortunio', 'InfortunioTipo', 'InfortunioDal',
    'PvTot', 'SquadreStag', 'Tit', 'Min',
] + COLONNE_STATS + ['Aggiornato']


def safe_int(x):
    v = pd.to_numeric(x, errors='coerce')
    return 0 if pd.isna(v) else int(v)


def safe_float(x):
    v = pd.to_numeric(str(x).replace(',', '.'), errors='coerce')
    return 0.0 if pd.isna(v) else float(v)


def pulisci_testo(valore):
    """Toglie gli apostrofi raddoppiati del CSV sorgente: Costa d''Avorio."""
    testo = str(valore or "").strip()
    if testo.lower() in ('nan', 'nat', 'none'):
        return ""
    return testo.replace("''", "'")


def errore(messaggio):
    print(f"❌ {messaggio}")
    if STRICT:
        sys.exit(1)


# ----------------------------------------------------------------------
# CARICAMENTO SORGENTI
# ----------------------------------------------------------------------
def carica_statistiche(percorso="Statistiche.xlsx"):
    """(stats_per_id, stats_per_nome) dalla stagione appena conclusa."""
    if not os.path.exists(percorso):
        errore(f"{percorso} mancante: senza statistiche il listone e' cieco.")
        return {}, {}

    try:
        df = pd.read_excel(percorso, header=1)
    except Exception as e:
        errore(f"Errore lettura {percorso}: {e}")
        return {}, {}

    mancanti = [c for c in COLONNE_STATS if c not in df.columns]
    if mancanti:
        errore(f"{percorso} non contiene le colonne attese: {mancanti}")
        return {}, {}

    per_id, per_nome = {}, {}
    for _, row in df.iterrows():
        record = {c: row.get(c) for c in COLONNE_STATS}
        record['R'] = str(row.get('R', '')).strip().upper()
        if 'Id' in df.columns:
            per_id[clean_id(row['Id'])] = record
        chiave = normalize_str(row.get('Nome', ''))
        if chiave:
            precedente = per_nome.get(chiave)
            if precedente is None or safe_int(record['Pv']) > safe_int(precedente['Pv']):
                per_nome[chiave] = record

    print(f"✅ Statistiche caricate: {len(per_id)} giocatori per Id.")
    return per_id, per_nome


def trova_file_quotazioni():
    """Il file quotazioni piu' recente, per nome. Aggiungere quello nuovo
    basta: viene preso da solo, il vecchio si puo' cancellare."""
    candidati = sorted(glob.glob("Quotazioni_Fantacalcio_Stagione_*.xlsx"), reverse=True)
    return candidati[0] if candidati else None


def carica_quotazioni(percorso=None):
    percorso = percorso or trova_file_quotazioni()
    if not percorso or not os.path.exists(percorso):
        errore("Nessun file Quotazioni_Fantacalcio_Stagione_*.xlsx trovato.")
        return {}

    print(f"📄 File quotazioni in uso: {percorso}")
    try:
        df = pd.read_excel(percorso, header=1)
    except Exception as e:
        errore(f"Errore lettura {percorso}: {e}")
        return {}

    if 'Id' not in df.columns:
        errore(f"{percorso} non ha la colonna Id: join impossibile.")
        return {}

    quote = {}
    for _, row in df.iterrows():
        quote[clean_id(row['Id'])] = {
            'Nome': row.get('Nome'),
            'R': str(row.get('R', '')).strip().upper(),
            'RM': row.get('RM'),
            'Squadra': row.get('Squadra'),
            'Qt.A': row.get('Qt.A'),
            'Qt.I': row.get('Qt.I'),
            # Mantra e FVM ufficiale vengono da QUI, non piu' dal vecchio CSV:
            # quello e' fermo alla stagione scorsa e portava valori scaduti.
            'Qt.M': row.get('Qt.A M'),
            'Diff.M': row.get('Diff.M'),
            'FVM': row.get('FVM'),
            'FVM.M': row.get('FVM M'),
        }
    print(f"✅ Quotazioni caricate: {len(quote)} giocatori.")
    return quote


def carica_anagrafica(percorso="Lista-FantaAsta-Fantacalcio.csv"):
    """CSV senza intestazione: serve solo per foto, piede, nazionalita',
    data di nascita e NOME COMPLETO (prezioso per agganciare l'API)."""
    if not os.path.exists(percorso):
        print(f"⚠️ {percorso} assente: niente foto/anagrafica.")
        return pd.DataFrame()

    try:
        with open(percorso, 'r', encoding='utf-8-sig', errors='ignore') as f:
            prima_riga = f.readline()
        sep = ';' if ';' in prima_riga else ','
        df = pd.read_csv(percorso, sep=sep, header=None, dtype=str,
                         encoding='utf-8-sig', on_bad_lines='skip')
    except Exception as e:
        print(f"⚠️ Errore lettura {percorso}: {e}")
        return pd.DataFrame()

    if len(df.columns) > 19:
        df = df.iloc[:, :19]
    while len(df.columns) < 19:
        df[len(df.columns)] = ""
    df.columns = COLONNE_CSV_BASE
    df['Id'] = df['Id'].apply(clean_id)
    print(f"✅ Anagrafica: {len(df)} righe.")
    return df


# ----------------------------------------------------------------------
# COSTRUZIONE LISTONE
# ----------------------------------------------------------------------
def costruisci_listone(quotazioni, df_extra):
    extra_per_id = {}
    if df_extra is not None and not df_extra.empty:
        for _, row in df_extra.iterrows():
            extra_per_id[clean_id(row['Id'])] = row

    squadre_note = {normalize_str(q['Squadra']) for q in quotazioni.values()}
    righe = []

    for pid, q in quotazioni.items():
        ruolo = q['R']
        if ruolo not in ('P', 'D', 'C', 'A'):
            continue

        riga = {c: "" for c in COLONNE_MASTER}
        riga['Id'] = pid
        riga['Nome'] = pulisci_testo(q['Nome'])
        riga['Nome_Breve'] = riga['Nome']
        riga['Nome_Completo'] = riga['Nome']
        riga['R'] = ruolo
        riga['Ruolo_Esteso'] = pulisci_testo(q.get('RM'))
        riga['Squadra'] = pulisci_testo(q['Squadra'])
        for campo in ('Qt.A', 'Qt.I', 'Qt.M', 'Diff.M', 'FVM.M'):
            riga[campo] = q.get(campo)
        riga['FVM_Ufficiale'] = safe_float(q.get('FVM'))

        extra = extra_per_id.get(pid)
        if extra is not None:
            for campo in ('Nome_Breve', 'Nome_Completo', 'Piede',
                          'DataNascita', 'PhotoURL'):
                valore = pulisci_testo(extra.get(campo))
                if valore:
                    riga[campo] = valore
            # Nel CSV sorgente qualche riga ha la nazionalita' sfasata e ci
            # finisce il nome di una squadra (Pessina Mas. -> "Bologna").
            nazione = pulisci_testo(extra.get('Nazionalita'))
            if nazione and normalize_str(nazione) not in squadre_note:
                riga['Nazionalita'] = nazione
            if not riga['Ruolo_Esteso']:
                riga['Ruolo_Esteso'] = pulisci_testo(extra.get('Ruolo_Esteso'))

        # I nuovi acquisti non sono nel CSV vecchio: la foto Fantacalcio si
        # costruisce dall'Id, che e' lo stesso usato nell'URL ufficiale.
        if not riga['PhotoURL'] and pid.isdigit():
            riga['PhotoURL'] = (
                f"https://content.fantacalcio.it/web/campioncini/21/card/{pid}.png")

        righe.append(riga)

    df = pd.DataFrame(righe, columns=COLONNE_MASTER)
    arricchiti = sum(1 for pid in quotazioni if pid in extra_per_id)
    print(f"✅ Listone: {len(df)} giocatori ({arricchiti} con anagrafica).")
    return df


# ----------------------------------------------------------------------
# AGGANCIO API <-> LISTONE
# ----------------------------------------------------------------------
def costruisci_indice(df):
    """
    diretto:     nome normalizzato -> idx (tutte le varianti del nome)
    per_parola:  ogni parola > 2 lettere -> lista di candidati
    """
    diretto, per_parola = {}, {}
    for idx, riga in df.iterrows():
        ruolo = str(riga.get('R', '')).strip().upper()
        squadra = normalize_str(riga.get('Squadra', ''))

        varianti = set()
        for campo in ('Nome', 'Nome_Breve', 'Nome_Completo'):
            chiave = normalize_str(riga.get(campo, ''))
            if chiave:
                varianti.add(chiave)
                diretto.setdefault(chiave, idx)

        tutte_parole = set()
        for variante in varianti:
            tutte_parole.update(variante.split())

        for parola in tutte_parole:
            if len(parola) > 2:
                per_parola.setdefault(parola, []).append({
                    'idx': idx, 'ruolo': ruolo, 'squadra': squadra,
                    'parole': tutte_parole,
                })
    return diretto, per_parola


def _compatibile_di_ruolo(ruolo_listone, ruolo_api):
    """
    Fantacalcio e API classificano diversamente D/C/A (Orsolini e' C per uno e
    attaccante per l'altro): li' si tollera. Il portiere no: un P e un non-P
    non sono mai la stessa persona. E' la regola che impedisce a Filippo
    Terracciano (difensore) di prendersi le partite di Pietro (portiere).
    """
    if not ruolo_listone or not ruolo_api:
        return True
    return (ruolo_listone == 'P') == (ruolo_api == 'P')


def trova_riga(giocatore, diretto, per_parola):
    """(idx, motivo). idx None se non si trova o e' ambiguo."""
    nome_api = normalize_str(giocatore['nome'])
    if not nome_api:
        return None, 'vuoto'

    if nome_api in diretto:
        return diretto[nome_api], 'esatto'

    parole_api = nome_api.split()
    ruolo_api = str(giocatore.get('ruolo', '')).upper()
    squadra_api = normalize_str(giocatore.get('squadra', ''))

    for parola in sorted(parole_api, key=len, reverse=True):
        if len(parola) <= 2:
            continue
        candidati = per_parola.get(parola, [])
        if not candidati:
            continue

        # 1. il ruolo portiere e' vincolante
        candidati = [c for c in candidati
                     if _compatibile_di_ruolo(c['ruolo'], ruolo_api)]
        if not candidati:
            continue
        if len({c['idx'] for c in candidati}) == 1:
            return candidati[0]['idx'], 'cognome'

        # 2. nome proprio: confronto per PREFISSO, non per iniziale
        resto_api = [p for p in parole_api if p != parola]
        per_nome = []
        for c in candidati:
            resto_listone = [p for p in c['parole'] if p != parola]
            if not resto_listone:
                per_nome.append(c)
                continue
            if any(abbreviazione_compatibile(a, l)
                   for a in resto_api for l in resto_listone):
                per_nome.append(c)
        if per_nome:
            candidati = per_nome
        if len({c['idx'] for c in candidati}) == 1:
            return candidati[0]['idx'], 'nome'

        # 3. squadra
        per_squadra = [c for c in candidati if c['squadra'] == squadra_api]
        if per_squadra:
            candidati = per_squadra
        if len({c['idx'] for c in candidati}) == 1:
            return candidati[0]['idx'], 'squadra'

        return None, 'ambiguo'

    return None, 'assente'


def sincronizza_con_api(df, scout):
    """Aggiorna squadre, foto, gare saltate e indisponibili. Ogni blocco ha il
    suo try: se salta l'uno, gli altri vanno avanti (prima un solo except
    copriva tutto e un errore banale spegneva anche gli infortuni)."""
    id_api_riga, candidati_nuovi = {}, []

    try:
        squadre = sorted({str(x).strip() for x in df['Squadra'] if str(x).strip()})
        scout.carica_squadre_serie_a(squadre)
        giocatori_api = scout.sincronizza_rose_serie_a()
    except Exception as e:
        print(f"⚠️ Rose non sincronizzate: {e}")
        giocatori_api = []

    if giocatori_api:
        diretto, per_parola = costruisci_indice(df)
        aggiornati = ambigui = collisioni = 0
        motivi = {}

        for g in giocatori_api:
            idx, motivo = trova_riga(g, diretto, per_parola)
            motivi[motivo] = motivi.get(motivo, 0) + 1
            if idx is None:
                if motivo == 'ambiguo':
                    ambigui += 1
                else:
                    candidati_nuovi.append(g)
                continue

            api_id = g.get('api_id')
            if api_id:
                if api_id in id_api_riga:
                    collisioni += 1
                else:
                    id_api_riga[api_id] = idx
            scout.associa(df.loc[idx, 'Nome'], api_id)
            scout.associa(df.loc[idx, 'Nome_Completo'], api_id)

            if str(df.loc[idx, 'Squadra']).strip() != g['squadra']:
                df.loc[idx, 'Squadra'] = g['squadra']
                aggiornati += 1

        print(f"🔗 Agganci: {motivi} | squadre corrette: {aggiornati} | "
              f"ambigui scartati: {ambigui} | collisioni evitate: {collisioni}")

    # --- foto ufficiali, agganciate per id ---
    try:
        con_foto = 0
        for api_id, url in getattr(scout, 'foto_per_id', {}).items():
            idx = id_api_riga.get(api_id)
            if idx is not None and url:
                df.loc[idx, 'FotoAPI'] = url
                con_foto += 1
        if con_foto:
            print(f"📸 Foto agganciate a {con_foto} giocatori.")
    except Exception as e:
        print(f"⚠️ Foto non agganciate: {e}")

    # --- gare saltate, divise per natura dell'assenza ---
    try:
        storico = scout.storico_infortuni()
        agganciate = 0
        for api_id, record in storico.items():
            idx = id_api_riga.get(api_id)
            if idx is None:
                continue
            df.loc[idx, 'GareSaltate'] = int(record.get('gare_fisiche', 0))
            df.loc[idx, 'GareSaltateAltro'] = int(record.get('gare_altro', 0))
            df.loc[idx, 'MotivoStop'] = str(record.get('motivo', ''))[:60]
            df.loc[idx, 'MotivoAltro'] = str(record.get('motivo_altro', ''))[:60]
            agganciate += 1
        if storico:
            print(f"🏥 Gare saltate agganciate a {agganciate} giocatori.")
    except Exception as e:
        print(f"⚠️ Storico infortuni non recuperato: {e}")

    # --- indisponibili di oggi ---
    try:
        fermi = scout.infortuni_correnti()
        memoria = scout.cache.setdefault('infortuni', {})
        oggi = datetime.date.today().isoformat()
        attivi, segnati = set(), 0

        for api_id, info in fermi.items():
            chiave = str(api_id)
            attivi.add(chiave)
            motivo = info['motivo'] or info['tipo']
            precedente = memoria.get(chiave)
            # L'API dice PERCHE' e' fermo, non da quando: la data del primo
            # avvistamento la teniamo noi. Non si inventa un rientro.
            dal = precedente['dal'] if (precedente and precedente.get('motivo') == motivo) else oggi
            memoria[chiave] = {'dal': dal, 'motivo': motivo}

            idx = id_api_riga.get(api_id)
            if idx is None:
                continue
            df.loc[idx, 'InfortunioTipo'] = info['tipo']
            df.loc[idx, 'Infortunio'] = motivo
            df.loc[idx, 'InfortunioDal'] = dal
            segnati += 1

        for chiave in list(memoria):
            if chiave not in attivi:
                memoria.pop(chiave, None)
        if fermi:
            print(f"🚑 {segnati} indisponibili agganciati al listone.")
    except Exception as e:
        print(f"⚠️ Infortuni correnti non recuperati: {e}")

    return candidati_nuovi


# ----------------------------------------------------------------------
# AVVISO: chi e' nelle rose ma non nel listone
# ----------------------------------------------------------------------
def segnala_nuovi_arrivi(candidati, scout):
    veri = []
    for g in candidati[:MAX_VERIFICHE_AVVISO]:
        try:
            dati = scout._stats_giocatore(g['nome'], avviso=True)
        except Exception:
            dati = None
        if dati and dati.get('presenze', 0) >= PRESENZE_MINIME_AVVISO:
            veri.append({
                'nome': g['nome'], 'squadra': g['squadra'], 'ruolo': g['ruolo'],
                'presenze': dati['presenze'], 'gol': dati.get('gol', 0),
                'lega': dati.get('lega', ''),
            })
    veri.sort(key=lambda x: (-x['gol'], -x['presenze']))

    try:
        with open(FILE_AVVISI, 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"⚠️ Impossibile scrivere {FILE_AVVISI}: {e}")

    if veri:
        righe = ["⚠️ <b>Giocatori fuori dal listone</b>",
                 "Sono nelle rose di Serie A ma non nelle tue quotazioni:", ""]
        for g in veri[:15]:
            righe.append(f"• <b>{g['nome']}</b> ({g['squadra']}, {g['ruolo']}) — "
                         f"{g['presenze']} pres, {g['gol']} gol")
        if len(veri) > 15:
            righe.append(f"...e altri {len(veri) - 15}.")
        # Le quotazioni NON vanno mandate al bot: il bot mostra il Master, non
        # lo costruisce. Il file nuovo va messo in questa repo.
        righe += ["", "Scarica le quotazioni aggiornate da Fantacalcio e caricale "
                  "in <code>fanta-master-ai</code>: il motore le usa dalla notte dopo."]
        testo = "\n".join(righe)
        print(f"🔔 {len(veri)} giocatori nelle rose ma NON nel listone.")
    else:
        testo = ""
        print("✅ Nessun giocatore rilevante fuori dal listone.")

    try:
        with open(FILE_MESSAGGIO, 'w', encoding='utf-8') as f:
            f.write(testo)
    except Exception:
        pass
    return veri


# ----------------------------------------------------------------------
# FANTAMEDIA E VALORE
# ----------------------------------------------------------------------
def calcola_baseline_ruoli(stats_per_id):
    per_ruolo = {}
    for rec in stats_per_id.values():
        ruolo = rec.get('R', '')
        pv, fm = safe_int(rec.get('Pv')), safe_float(rec.get('Fm'))
        if ruolo in BASELINE_DEFAULT and pv >= 15 and fm > 0:
            per_ruolo.setdefault(ruolo, []).append(fm)

    baseline = {}
    for ruolo, default in BASELINE_DEFAULT.items():
        valori = sorted(per_ruolo.get(ruolo, []))
        baseline[ruolo] = round(valori[len(valori) // 2], 2) if len(valori) >= 10 else default
    print(f"📐 Baseline fantamedia per ruolo: {baseline}")
    return baseline


def fm_ponderata(fm, presenze, baseline):
    if not fm or fm <= 0:
        return None
    return (max(0, int(presenze)) * fm + K_SHRINK * baseline) / (max(0, int(presenze)) + K_SHRINK)


def stima_fvm(best_qt, fm_val, ruolo, squadra, baseline=None):
    """Modello interno: quotazione + peso dei bonus. Resta una STIMA, e da
    quest'anno non e' piu' lei a decidere i prezzi (vedi FONTE_FVM)."""
    if fm_val is None or fm_val <= 0:
        if best_qt <= 1:
            return 1.0
        fm_val = (baseline or BASELINE_DEFAULT).get(ruolo, 6.0)

    if ruolo == 'A':
        base = (best_qt * 9.5) + (max(0, fm_val - 5.5) ** 2.2) * 35
    elif ruolo == 'C':
        base = (best_qt * 7.0) + (max(0, fm_val - 5.5) ** 2.0) * 25
    elif ruolo == 'D':
        base = (best_qt * 4.0) + (max(0, fm_val - 5.5) ** 1.5) * 15
    elif ruolo == 'P':
        base = (best_qt * 4.5) + (max(0, fm_val - 5.0) ** 1.5) * 15
    else:
        base = best_qt * 3.0

    if squadra in BIG_TEAMS and best_qt >= 8.0:
        base *= 1.20
    return round(min(1000.0, max(1.0, float(base))), 1)


def scegli_fvm(ufficiale, stima):
    ufficiale = max(0.0, float(ufficiale or 0))
    stima = max(1.0, float(stima or 1))
    if FONTE_FVM == 'stima' or ufficiale <= 0:
        return round(stima, 1)
    if FONTE_FVM == 'misto':
        return round((ufficiale ** 0.65) * (stima ** 0.35), 1)
    return round(ufficiale, 1)


def calcola_prezzi(df):
    """
    Converte il valore in crediti: per ogni ruolo si distribuisce la quota di
    budget della lega fra i giocatori che verranno davvero comprati.
    """
    prezzi = pd.Series(1.0, index=df.index)
    fvm = pd.to_numeric(df['FVM'], errors='coerce').fillna(0.0)

    for ruolo, quota in QUOTE_RUOLO.items():
        mask = df['R'] == ruolo
        if not mask.any():
            continue
        acquistabili = SLOT_RUOLO[ruolo] * SQUADRE_LEGA
        candidati = fvm[mask].sort_values(ascending=False).head(acquistabili)
        peso = candidati ** ESPONENTE_PREZZO
        if peso.sum() <= 0:
            continue

        monte = quota * BUDGET_LEGA * SQUADRE_LEGA
        quota_giocatore = ((peso / peso.sum()) * monte).clip(lower=1.0)
        prezzi.loc[quota_giocatore.index] = quota_giocatore

        # Chi resta fuori dai titolari non vale 1 credito d'ufficio: si
        # prolunga la stessa scala partendo dall'ultimo prezzo assegnato.
        fvm_taglio = candidati.iloc[-1]
        prezzo_taglio = quota_giocatore.iloc[-1]
        if fvm_taglio > 0:
            restanti = fvm[mask].drop(candidati.index)
            if not restanti.empty:
                prezzi.loc[restanti.index] = (
                    restanti * (prezzo_taglio / fvm_taglio)
                ).clip(lower=1.0, upper=float(prezzo_taglio))

    return prezzi.round(0).astype(int)


def trova_stats(id_giocatore, nome, ruolo, stats_per_id, stats_per_nome):
    record = stats_per_id.get(clean_id(id_giocatore))
    if record is not None:
        return record, 'id'
    record = stats_per_nome.get(normalize_str(nome))
    if record is not None:
        return record, 'nome'
    return None, None


# ----------------------------------------------------------------------
# VERIFICA FINALE
# ----------------------------------------------------------------------
def verifica(df):
    problemi = []
    if len(df) < 300:
        problemi.append(f"solo {len(df)} giocatori nel listone")
    squadre = df['Squadra'].nunique()
    if squadre != 20:
        problemi.append(f"{squadre} squadre invece di 20")
    if (df['Prezzo'] <= 0).any():
        problemi.append("prezzi non positivi")

    con_stats = int((pd.to_numeric(df['Pv'], errors='coerce').fillna(0) > 0).sum())
    print("─" * 55)
    print(f"📋 {len(df)} giocatori · {squadre} squadre · {con_stats} con statistiche reali")
    print(f"💰 Somma prezzi: {int(df['Prezzo'].sum())} cr "
          f"(monte lega di riferimento: {BUDGET_LEGA * SQUADRE_LEGA} cr sui titolari)")
    for ruolo in ('P', 'D', 'C', 'A'):
        gruppo = df[df['R'] == ruolo].nlargest(1, 'Prezzo')
        if not gruppo.empty:
            r = gruppo.iloc[0]
            print(f"   {ruolo}: piu' caro {r['Nome']} ({r['Squadra']}) {int(r['Prezzo'])} cr")

    if problemi:
        errore("Controlli finali falliti: " + "; ".join(problemi))
        return False
    return True


# ----------------------------------------------------------------------
def main():
    print("🚀 Master Engine V13 - fonti verificate, fatti separati dalle stime")
    scout = ScoutEngine()

    stats_per_id, stats_per_nome = carica_statistiche()
    quotazioni = carica_quotazioni()
    if not quotazioni:
        errore("Senza quotazioni non si costruisce nulla.")
        return 1

    df_extra = carica_anagrafica()
    df = costruisci_listone(quotazioni, df_extra)

    print("🌐 Sincronizzazione con API-Football...")
    candidati_nuovi = sincronizza_con_api(df, scout)
    # Si chiama SEMPRE, anche senza candidati: cosi' avviso.txt viene riscritto
    # (vuoto) e la notifica di ieri non parte una seconda volta.
    segnala_nuovi_arrivi(candidati_nuovi, scout)

    baseline = calcola_baseline_ruoli(stats_per_id)
    conteggio = {'id': 0, 'nome': 0, 'scout': 0, 'nessuno': 0}
    colonne = {c: [] for c in ['FVM', 'FVM_Stima', 'Scarto',
                               'PvTot', 'SquadreStag', 'Tit', 'Min'] + COLONNE_STATS}

    for _, row in df.iterrows():
        nome = str(row['Nome']).strip()
        nome_api = str(row['Nome_Completo'] or nome).strip()
        ruolo = str(row['R']).strip()
        squadra = str(row['Squadra']).strip()

        # Qt.A e' la quotazione attuale. Prendere il massimo fra Qt.A e Qt.I
        # gonfiava chi era partito caro e si era svalutato (un lungodegente).
        best_qt = safe_float(row['Qt.A']) or safe_float(row['Qt.I']) or 1.0

        record, metodo = trova_stats(row['Id'], nome, ruolo, stats_per_id, stats_per_nome)
        valori = {c: 0 for c in COLONNE_STATS}
        if record is not None:
            conteggio[metodo] += 1
            for c in COLONNE_STATS:
                valori[c] = (safe_float(record.get(c)) if c in COLONNE_DECIMALI
                             else safe_int(record.get(c)))

        pv = int(valori['Pv'])
        fm_grezza = float(valori['Fm']) if float(valori['Fm']) > 0 else None
        presenze_peso = pv

        if fm_grezza is None:
            try:
                proiezione = scout.calcola_fantamedia_proiettata(nome_api, ruolo)
            except Exception:
                proiezione = None
            if proiezione:
                conteggio['scout'] += 1
                fm_grezza = proiezione
                presenze_peso = K_SHRINK      # una stima pesa quanto la baseline
            elif record is None:
                conteggio['nessuno'] += 1

        base_ruolo = baseline.get(ruolo, 6.0)
        stima = stima_fvm(best_qt, fm_ponderata(fm_grezza, presenze_peso, base_ruolo),
                          ruolo, squadra, baseline)
        ufficiale = safe_float(row['FVM_Ufficiale'])
        fvm = scegli_fvm(ufficiale, stima)

        # Presenze totali di stagione: distingue chi non gioca da chi e'
        # arrivato a gennaio. Si chiede solo per i casi dubbi.
        presenze_totali, squadre_stagione, da_titolare, minuti = pv, 1, 0, 0
        if 0 < pv < PRESENZE_SOSPETTE:
            try:
                extra = scout.presenze_stagione(nome_api)
            except Exception:
                extra = None
            if extra:
                presenze_totali = max(pv, extra['totali'])
                squadre_stagione = extra['squadre']
                da_titolare = extra.get('da_titolare', 0)
                minuti = extra.get('minuti', 0)

        colonne['FVM'].append(fvm)
        colonne['FVM_Stima'].append(stima)
        colonne['Scarto'].append(round(stima / fvm, 2) if fvm > 0 else 0.0)
        colonne['PvTot'].append(int(presenze_totali))
        colonne['SquadreStag'].append(int(squadre_stagione))
        colonne['Tit'].append(int(da_titolare))
        colonne['Min'].append(int(minuti))
        for c in COLONNE_STATS:
            colonne[c].append(round(fm_grezza, 2) if (c == 'Fm' and fm_grezza) else
                              (0.0 if c == 'Fm' else valori[c]))

    for col, valori in colonne.items():
        df[col] = valori

    df['GareSaltate'] = pd.to_numeric(df['GareSaltate'], errors='coerce').fillna(0).astype(int)
    df['GareSaltateAltro'] = pd.to_numeric(
        df['GareSaltateAltro'], errors='coerce').fillna(0).astype(int)
    df['Aggiornato'] = datetime.date.today().isoformat()
    df['Prezzo'] = calcola_prezzi(df)
    df = df[COLONNE_MASTER].fillna("")

    df.to_csv(FILE_MASTER, sep=';', index=False)
    scout.salva_cache()

    print("─" * 55)
    print(f"📊 Statistiche: {conteggio['id']} per Id | {conteggio['nome']} per nome | "
          f"{conteggio['scout']} proiezioni | {conteggio['nessuno']} senza dati")
    print(f"📡 Chiamate API: {scout.chiamate} (di cui {scout.lookup} lookup giocatore)"
          + (" — QUOTA ESAURITA" if scout.quota_esaurita else ""))
    if scout.anomalie:
        print(f"⚠️ {len(scout.anomalie)} dati fuori scala scartati: "
              + "; ".join(scout.anomalie[:5]))
    print(f"🎯 Fonte del valore: {FONTE_FVM}")

    return 0 if verifica(df) else 1


if __name__ == '__main__':
    sys.exit(main())

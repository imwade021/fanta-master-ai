import pandas as pd
import numpy as np
import os
import re
import unicodedata
from scout_engine import ScoutEngine

BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

COLONNE_MASTER = [
    'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I',
    'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita',
    'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
]

COLONNE_STATS = ['Pv', 'Mv', 'Fm', 'Gf', 'Ass', 'Amm', 'Esp']


def normalize_str(s):
    if pd.isna(s): return ""
    s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return " ".join(s.split())


def clean_id(x):
    """Normalizza l'Id come stringa, togliendo BOM, spazi e decimali (es. '4431.0')."""
    s = str(x).replace('\ufeff', '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def match_nomi_abbreviati(nome_lungo, nome_breve):
    n1 = normalize_str(nome_lungo).split()
    n2 = normalize_str(nome_breve).split()
    if not n1 or not n2: return False
    return n1[-1] == n2[-1] and n1[0][0] == n2[0][0]


def safe_int(x):
    v = pd.to_numeric(x, errors='coerce')
    return 0 if pd.isna(v) else int(v)


def safe_float(x):
    v = pd.to_numeric(str(x).replace(',', '.'), errors='coerce')
    return 0.0 if pd.isna(v) else float(v)


# ----------------------------------------------------------------------
# CARICAMENTO SORGENTI
# ----------------------------------------------------------------------
def carica_statistiche(percorso="Statistiche.xlsx"):
    """
    Restituisce (stats_per_id, stats_per_nome).
    Il file Statistiche_Fantacalcio contiene le colonne reali: Pv, Mv, Fm, Gf, Ass, Amm, Esp.
    """
    if not os.path.exists(percorso):
        print(f"⚠️ {percorso} mancante: le statistiche storiche non verranno iniettate.")
        return {}, {}

    try:
        df = pd.read_excel(percorso, header=1)
    except Exception as e:
        print(f"⚠️ Errore lettura {percorso}: {e}")
        return {}, {}

    mancanti = [c for c in COLONNE_STATS if c not in df.columns]
    if mancanti:
        print(f"⚠️ {percorso} non contiene le colonne statistiche attese: {mancanti}")
        return {}, {}

    per_id, per_nome = {}, {}
    for _, row in df.iterrows():
        record = {c: row.get(c) for c in COLONNE_STATS}
        record['R'] = str(row.get('R', '')).strip().upper()

        if 'Id' in df.columns:
            per_id[clean_id(row['Id'])] = record

        chiave = normalize_str(row.get('Nome', ''))
        if chiave:
            # A parita' di nome tiene chi ha piu' presenze
            precedente = per_nome.get(chiave)
            if precedente is None or safe_int(record['Pv']) > safe_int(precedente['Pv']):
                per_nome[chiave] = record

    print(f"✅ Statistiche caricate: {len(per_id)} giocatori indicizzati per Id.")
    return per_id, per_nome


def carica_quotazioni(percorso="Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"):
    """Quotazioni ufficiali aggiornate, indicizzate per Id (Qt.A / Qt.I)."""
    if not os.path.exists(percorso):
        return {}
    try:
        df = pd.read_excel(percorso, header=1)
    except Exception as e:
        print(f"⚠️ Errore lettura {percorso}: {e}")
        return {}

    if 'Id' not in df.columns:
        return {}

    quote = {}
    for _, row in df.iterrows():
        quote[clean_id(row['Id'])] = {
            'Qt.A': row.get('Qt.A'),
            'Qt.I': row.get('Qt.I'),
            'Squadra': row.get('Squadra'),
        }
    print(f"✅ Quotazioni caricate: {len(quote)} giocatori.")
    return quote


def carica_listone_base(percorso="Lista-FantaAsta-Fantacalcio.csv"):
    with open(percorso, 'r', encoding='utf-8-sig', errors='ignore') as f:
        first_line = f.readline()
    sep = ';' if ';' in first_line else ','

    df = pd.read_csv(percorso, sep=sep, header=None, dtype=str,
                     encoding='utf-8-sig', on_bad_lines='skip')

    if len(df.columns) > 19:
        df = df.iloc[:, :19]
    while len(df.columns) < 19:
        df[len(df.columns)] = ""

    df.columns = COLONNE_MASTER
    df['Id'] = df['Id'].apply(clean_id)
    df['R'] = df['R'].astype(str).str.strip().str.upper()
    return df[df['R'].isin(['P', 'D', 'C', 'A'])].reset_index(drop=True)


# ----------------------------------------------------------------------
# LOOKUP STATISTICHE: Id -> nome esatto -> nome abbreviato
# ----------------------------------------------------------------------
def trova_stats(id_giocatore, nome, ruolo, stats_per_id, stats_per_nome):
    record = stats_per_id.get(clean_id(id_giocatore))
    if record is not None:
        return record, 'id'

    chiave = normalize_str(nome)
    record = stats_per_nome.get(chiave)
    if record is not None:
        return record, 'nome'

    for chiave_stats, rec in stats_per_nome.items():
        if match_nomi_abbreviati(nome, chiave_stats) and rec.get('R', '') == ruolo:
            return rec, 'nome_abbreviato'

    return None, None


# ----------------------------------------------------------------------
# CALCOLO FVM
# ----------------------------------------------------------------------
def calcola_fvm(best_qt, fm_val, ruolo, squadra, scout, nome):
    if fm_val is None or fm_val <= 0:
        if best_qt <= 1:
            is_prospetto = scout.verifica_prospetto_giovanile(nome, squadra)
            base_fvm = 15.0 if is_prospetto else 1.0
            return round(min(500.0, max(1.0, base_fvm)), 1), None
        fm_val = 6.0
        base_fvm = best_qt * 4.0
        return round(min(500.0, max(1.0, base_fvm)), 1), fm_val

    if ruolo == 'A':
        base_fvm = (best_qt * 9.5) + (max(0, fm_val - 5.5) ** 2.2) * 35
    elif ruolo == 'C':
        base_fvm = (best_qt * 7.0) + (max(0, fm_val - 5.5) ** 2.0) * 25
    elif ruolo == 'D':
        base_fvm = (best_qt * 4.0) + (max(0, fm_val - 5.5) ** 1.5) * 15
    elif ruolo == 'P':
        base_fvm = (best_qt * 4.5) + (max(0, fm_val - 5.0) ** 1.5) * 15
    else:
        base_fvm = best_qt * 3.0

    if squadra in BIG_TEAMS and best_qt >= 8.0:
        base_fvm *= 1.20

    return round(min(500.0, max(1.0, float(base_fvm))), 1), fm_val


# ----------------------------------------------------------------------
def main():
    print("🚀 Avvio Master Engine V12.0 - JOIN STATISTICHE PER ID...")
    scout = ScoutEngine()

    stats_per_id, stats_per_nome = carica_statistiche()
    quotazioni = carica_quotazioni()

    csv_file = "Lista-FantaAsta-Fantacalcio.csv"
    if not os.path.exists(csv_file):
        print(f"❌ File base {csv_file} mancante.")
        return

    df_listone = carica_listone_base(csv_file)
    print(f"✅ Listone base: {len(df_listone)} giocatori.")

    # Refresh quotazioni ufficiali per Id (le quotazioni cambiano durante la stagione)
    aggiornate = 0
    for idx, row in df_listone.iterrows():
        q = quotazioni.get(row['Id'])
        if q:
            if not pd.isna(q['Qt.A']):
                df_listone.loc[idx, 'Qt.A'] = str(q['Qt.A'])
            if not pd.isna(q['Qt.I']):
                df_listone.loc[idx, 'Qt.I'] = str(q['Qt.I'])
            aggiornate += 1
    print(f"🔄 Quotazioni aggiornate da Excel per {aggiornate} giocatori.")

    # ------------------------------------------------------------------
    # SINCRONIZZAZIONE ROSE VIA API
    # ------------------------------------------------------------------
    print("🌐 Sincronizzazione API con DEDUPLICAZIONE...")
    try:
        nuovi_giocatori_api = scout.sincronizza_rose_serie_a()
        if nuovi_giocatori_api:
            indice_nomi = {normalize_str(n): i for i, n in df_listone['Nome'].items()}
            righe_nuove = []

            for g_api in nuovi_giocatori_api:
                nome_api = g_api['nome']
                norm_api = normalize_str(nome_api)

                idx_match = indice_nomi.get(norm_api)
                if idx_match is None:
                    for nome_norm, i in indice_nomi.items():
                        if match_nomi_abbreviati(nome_norm, norm_api):
                            idx_match = i
                            break

                if idx_match is not None:
                    df_listone.loc[idx_match, 'Squadra'] = g_api['squadra']
                elif len(nome_api) > 4 and not nome_api.startswith('.'):
                    righe_nuove.append({
                        'Id': str(9000 + len(df_listone) + len(righe_nuove)),
                        'Nome_Breve': nome_api,
                        'Nome': nome_api,
                        'R': g_api['ruolo'],
                        'Ruolo_Esteso': g_api['ruolo'],
                        'Qt.A': '1',
                        'Qt.I': '1',
                        'Squadra': g_api['squadra'],
                        'FVM': '1.0'
                    })

            if righe_nuove:
                df_listone = pd.concat([df_listone, pd.DataFrame(righe_nuove)], ignore_index=True)
                print(f"➕ {len(righe_nuove)} giocatori aggiunti dall'API.")
    except Exception as e:
        print(f"⚠️ Avviso API: {e}")

    # ------------------------------------------------------------------
    # INIEZIONE STATISTICHE + CALCOLO FVM
    # ------------------------------------------------------------------
    colonne_out = {c: [] for c in ['FVM'] + COLONNE_STATS}
    conteggio = {'id': 0, 'nome': 0, 'nome_abbreviato': 0, 'scout': 0, 'nessuno': 0}

    for _, row in df_listone.iterrows():
        nome = str(row['Nome']).strip()
        ruolo = str(row['R']).strip()
        squadra = str(row['Squadra']).strip()

        qt_i = safe_float(row['Qt.I']) or 1.0
        qt_a = safe_float(row['Qt.A']) or qt_i
        best_qt = max(qt_i, qt_a)

        record, metodo = trova_stats(row['Id'], nome, ruolo, stats_per_id, stats_per_nome)

        pv = mv = fm_storico = gf = ass = amm = esp = 0
        fm_val = None

        if record is not None:
            conteggio[metodo] += 1
            pv = safe_int(record['Pv'])
            mv = safe_float(record['Mv'])
            fm_storico = safe_float(record['Fm'])
            gf = safe_int(record['Gf'])
            ass = safe_int(record['Ass'])
            amm = safe_int(record['Amm'])
            esp = safe_int(record['Esp'])
            if fm_storico > 0:
                fm_val = fm_storico

        # Nessuno storico in Serie A: proiezione dello scout (estero / nuovi arrivi)
        if fm_val is None:
            try:
                fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fm_val:
                    conteggio['scout'] += 1
                elif record is None:
                    conteggio['nessuno'] += 1
            except Exception:
                fm_val = None

        fvm_finale, fm_usata = calcola_fvm(best_qt, fm_val, ruolo, squadra, scout, nome)

        colonne_out['FVM'].append(fvm_finale)
        colonne_out['Pv'].append(pv)
        colonne_out['Mv'].append(mv)
        colonne_out['Fm'].append(fm_storico if fm_storico > 0 else (round(fm_usata, 2) if fm_usata else 0.0))
        colonne_out['Gf'].append(gf)
        colonne_out['Ass'].append(ass)
        colonne_out['Amm'].append(amm)
        colonne_out['Esp'].append(esp)

    for col, valori in colonne_out.items():
        df_listone[col] = valori

    df_listone = df_listone.fillna("")
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)

    scout.salva_cache()

    con_stats = sum(1 for v in colonne_out['Pv'] if v > 0)
    print("─" * 50)
    print(f"📊 Match statistiche: {conteggio['id']} per Id | {conteggio['nome']} per nome | "
          f"{conteggio['nome_abbreviato']} per nome abbreviato")
    print(f"📊 Proiezioni scout: {conteggio['scout']} | Senza dati: {conteggio['nessuno']}")
    print(f"📡 Chiamate API usate in questo run: {scout.chiamate}"
          + (" (quota giornaliera esaurita)" if scout.quota_esaurita else ""))
    print(f"✅ Lista_Finale_Master.csv rigenerato: {len(df_listone)} giocatori, "
          f"{con_stats} con statistiche reali.")


if __name__ == '__main__':
    main()

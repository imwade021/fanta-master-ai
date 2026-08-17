import pandas as pd
import numpy as np
import os
import re
import glob
import json
import datetime
import unicodedata
from scout_engine import ScoutEngine

BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

COLONNE_MASTER = [
    'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I',
    'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita',
    'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
]

COLONNE_STATS = ['Pv', 'Mv', 'Fm', 'Gf', 'Gs', 'Rp', 'Rc', 'R+', 'R-', 'Ass', 'Amm', 'Esp']
COLONNE_DECIMALI = {'Mv', 'Fm'}

# Parametri lega per il prezzo consigliato (sovrascrivibili da variabili d'ambiente)
SQUADRE_LEGA = int(os.getenv("FANTA_SQUADRE_LEGA", "8"))
BUDGET_LEGA = int(os.getenv("FANTA_BUDGET", "500"))
QUOTE_RUOLO = {'P': 0.08, 'D': 0.14, 'C': 0.28, 'A': 0.50}
SLOT_RUOLO = {'P': 3, 'D': 8, 'C': 8, 'A': 6}

# Quanto pesa la media di ruolo rispetto alle presenze reali: con K=8, un giocatore
# con 8 presenze vale meta' se stesso e meta' baseline.
K_SHRINK = 8
BASELINE_DEFAULT = {'P': 5.40, 'D': 5.80, 'C': 6.00, 'A': 6.20}

# Presenze totali di stagione (tutte le competizioni e squadre): distingue chi
# non gioca da chi e' arrivato nel mercato di gennaio.
PRESENZE_SOSPETTE = int(os.getenv("FANTA_PRESENZE_SOSPETTE", "26"))

# L'API dice PERCHE' e' fermo, non quando rientra: quella data non e' un dato
# disponibile e non va inventata. Si registra solo da quando e' fermo.

# Lettere che la normalizzazione standard cancella invece di convertire:
# senza questa tabella "Hojlund" e "Højlund" non si riconoscono fra loro.
LETTERE_SPECIALI = str.maketrans({
    'ø': 'o', 'Ø': 'O', 'đ': 'd', 'Đ': 'D', 'ł': 'l', 'Ł': 'L',
    'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ð': 'd', 'þ': 'th',
    'ı': 'i', 'İ': 'I',   # turco: la i senza punto veniva cancellata (Yildiz)
    'ħ': 'h', 'ŧ': 't', 'ĸ': 'k',
})


def normalize_str(s):
    if pd.isna(s): return ""
    s = str(s).translate(LETTERE_SPECIALI)
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
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


def trova_file_quotazioni():
    """Prende il file quotazioni piu' recente, qualunque stagione abbia nel nome."""
    candidati = sorted(glob.glob("Quotazioni_Fantacalcio_Stagione_*.xlsx"), reverse=True)
    return candidati[0] if candidati else None


def carica_quotazioni(percorso=None):
    """Quotazioni ufficiali aggiornate, indicizzate per Id (Qt.A / Qt.I)."""
    percorso = percorso or trova_file_quotazioni()
    if not percorso or not os.path.exists(percorso):
        print("⚠️ Nessun file Quotazioni_Fantacalcio_Stagione_*.xlsx trovato: "
              "le quotazioni restano quelle del listone base.")
        return {}
    print(f"📄 File quotazioni in uso: {percorso}")
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
            'Nome': row.get('Nome'),
            'R': str(row.get('R', '')).strip().upper(),
            'RM': row.get('RM'),
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


PRESENZE_MINIME_AVVISO = int(os.getenv("FANTA_PRESENZE_AVVISO", "5"))
MAX_VERIFICHE_AVVISO = int(os.getenv("FANTA_MAX_VERIFICHE", "300"))
FILE_AVVISI = "avvisi.json"
FILE_MESSAGGIO = "avviso.txt"


def segnala_nuovi_arrivi(candidati, scout):
    """
    Fra i giocatori visti nelle rose ma assenti dal listone, tiene solo quelli
    con un minimo di carriera vera: cosi' l'avviso non si riempie di primavera
    e terzi portieri. Scrive avvisi.json, che l'Action usa per la notifica.
    """
    veri = []
    for g in candidati[:MAX_VERIFICHE_AVVISO]:
        try:
            dati = scout._stats_giocatore(g['nome'])
        except Exception:
            dati = None
        if dati and dati.get('presenze', 0) >= PRESENZE_MINIME_AVVISO:
            veri.append({
                'nome': g['nome'],
                'squadra': g['squadra'],
                'ruolo': g['ruolo'],
                'presenze': dati['presenze'],
                'gol': dati.get('gol', 0),
                'lega': dati.get('lega', ''),
            })

    veri.sort(key=lambda x: (-x['gol'], -x['presenze']))
    try:
        with open(FILE_AVVISI, 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"⚠️ Impossibile scrivere {FILE_AVVISI}: {e}")

    # Messaggio gia' pronto: il workflow deve solo spedirlo, senza script inline
    if veri:
        righe = ["⚠️ <b>Giocatori fuori dal listone</b>",
                 "Sono nelle rose di Serie A ma non nelle tue quotazioni:", ""]
        for g in veri[:15]:
            righe.append(f"• <b>{g['nome']}</b> ({g['squadra']}, {g['ruolo']}) — "
                         f"{g['presenze']} pres, {g['gol']} gol")
        if len(veri) > 15:
            righe.append(f"...e altri {len(veri) - 15}.")
        righe += ["", "Scarica le quotazioni aggiornate da Fantacalcio "
                      "e mandami il file qui in chat."]
        testo = "\n".join(righe)
    else:
        testo = ""

    try:
        with open(FILE_MESSAGGIO, 'w', encoding='utf-8') as f:
            f.write(testo)
    except Exception:
        pass

    if veri:
        print(f"🔔 {len(veri)} giocatori nelle rose ma NON nel listone "
              f"(quotazioni forse da aggiornare):")
        for g in veri[:10]:
            print(f"   • {g['nome']} ({g['squadra']}, {g['ruolo']}) — "
                  f"{g['presenze']} pres, {g['gol']} gol in {g['lega']}")
    else:
        print("✅ Nessun giocatore rilevante fuori dal listone.")
    return veri


def costruisci_listone(quotazioni, df_extra):
    """
    Il file quotazioni definisce CHI e' in Serie A quest'anno e in che squadra.
    Il vecchio CSV serve solo ad arricchire (foto, piede, nazionalita') per Id.
    """
    extra_per_id = {}
    if df_extra is not None and not df_extra.empty:
        for _, row in df_extra.iterrows():
            extra_per_id[clean_id(row['Id'])] = row

    righe = []
    for pid, q in quotazioni.items():
        ruolo = q['R']
        if ruolo not in ('P', 'D', 'C', 'A'):
            continue

        extra = extra_per_id.get(pid)
        riga = {c: "" for c in COLONNE_MASTER}
        riga['Id'] = pid
        riga['Nome'] = str(q['Nome']).strip()
        riga['R'] = ruolo
        riga['Ruolo_Esteso'] = str(q.get('RM') or "").strip()
        riga['Squadra'] = str(q['Squadra']).strip()
        riga['Qt.A'] = q['Qt.A']
        riga['Qt.I'] = q['Qt.I']
        riga['Nome_Breve'] = riga['Nome']

        if extra is not None:
            for campo in ['Nome_Breve', 'Piede', 'Nazionalita', 'DataNascita',
                          'PhotoURL', 'Qt.M', 'Diff.M', 'FVM.M']:
                valore = str(extra.get(campo, "") or "").strip()
                if valore:
                    riga[campo] = valore
            if not riga['Ruolo_Esteso']:
                riga['Ruolo_Esteso'] = str(extra.get('Ruolo_Esteso', "") or "").strip()

        righe.append(riga)

    df = pd.DataFrame(righe, columns=COLONNE_MASTER)
    arricchiti = sum(1 for pid in quotazioni if pid in extra_per_id)
    print(f"✅ Listone costruito dalle quotazioni: {len(df)} giocatori "
          f"({arricchiti} arricchiti con foto/anagrafica dal CSV).")
    return df


def calcola_baseline_ruoli(stats_per_id):
    """Fantamedia mediana per ruolo fra chi ha giocato almeno 15 partite."""
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
    """Avvicina la fantamedia alla media di ruolo quando le presenze sono poche."""
    if not fm or fm <= 0:
        return None
    presenze = max(0, int(presenze))
    return (presenze * fm + K_SHRINK * baseline) / (presenze + K_SHRINK)


def calcola_prezzi(df):
    """
    Converte la FVM in crediti spendibili: per ogni ruolo distribuisce la quota
    di budget della lega fra i giocatori che verranno realmente comprati.
    """
    prezzi = pd.Series(1.0, index=df.index)
    fvm = pd.to_numeric(df['FVM'], errors='coerce').fillna(0.0)

    for ruolo, quota in QUOTE_RUOLO.items():
        mask = df['R'] == ruolo
        if not mask.any():
            continue

        acquistabili = SLOT_RUOLO[ruolo] * SQUADRE_LEGA
        candidati = fvm[mask].sort_values(ascending=False).head(acquistabili)
        peso = candidati ** 1.25
        if peso.sum() <= 0:
            continue

        # Crediti che l'intera lega spendera' su questo ruolo
        monte = quota * BUDGET_LEGA * SQUADRE_LEGA
        quota_giocatore = ((peso / peso.sum()) * monte).clip(lower=1.0)
        prezzi.loc[quota_giocatore.index] = quota_giocatore

        # Chi resta fuori dai titolari non vale 1 credito d'ufficio: si prolunga
        # la stessa scala del gruppo, partendo dall'ultimo prezzo assegnato.
        fvm_taglio = candidati.iloc[-1]
        prezzo_taglio = quota_giocatore.iloc[-1]
        if fvm_taglio > 0:
            restanti = fvm[mask].drop(candidati.index)
            if not restanti.empty:
                prezzi.loc[restanti.index] = (restanti * (prezzo_taglio / fvm_taglio)).clip(
                    lower=1.0, upper=float(prezzo_taglio))

    return prezzi.round(0).astype(int)


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
def calcola_fvm(best_qt, fm_val, ruolo, squadra, scout, nome, baseline=None):
    """fm_val e' gia' ponderata per le presenze (vedi fm_ponderata)."""
    if fm_val is None or fm_val <= 0:
        if best_qt <= 1:
            is_prospetto = scout.verifica_prospetto_giovanile(nome, squadra)
            base_fvm = 15.0 if is_prospetto else 1.0
            return round(min(1000.0, max(1.0, base_fvm)), 1), None

        # Senza statistiche si assume il rendimento MEDIO del suo ruolo, non un
        # forfait: la quotazione di Fantacalcio contiene gia' un'aspettativa.
        # Il vecchio "quotazione x 4" schiacciava a 5 crediti giocatori che il
        # mercato paga 45 (es. un nuovo arrivo dall'estero).
        fm_val = (baseline or BASELINE_DEFAULT).get(ruolo, 6.0)

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

    return round(min(1000.0, max(1.0, float(base_fvm))), 1), fm_val


# ----------------------------------------------------------------------
def main():
    print("🚀 Avvio Master Engine V12.0 - JOIN STATISTICHE PER ID...")
    scout = ScoutEngine()

    stats_per_id, stats_per_nome = carica_statistiche()
    quotazioni = carica_quotazioni()

    csv_file = "Lista-FantaAsta-Fantacalcio.csv"
    df_extra = carica_listone_base(csv_file) if os.path.exists(csv_file) else pd.DataFrame()
    if df_extra.empty:
        print("⚠️ CSV anagrafica assente: niente foto/piede/nazionalita'.")

    if quotazioni:
        df_listone = costruisci_listone(quotazioni, df_extra)
    elif not df_extra.empty:
        print("⚠️ Nessuna quotazione: ripiego sul CSV (rose potenzialmente vecchie).")
        df_listone = df_extra
    else:
        print("❌ Nessuna fonte disponibile: servono le quotazioni o il CSV.")
        return

    # ------------------------------------------------------------------
    # SINCRONIZZAZIONE ROSE VIA API
    # ------------------------------------------------------------------
    print("🌐 Sincronizzazione rose via API...")
    id_api_riga = {}
    try:
        squadre_listone = sorted({str(x).strip() for x in df_listone['Squadra'] if str(x).strip()})
        scout.carica_squadre_serie_a(squadre_listone)
        giocatori_api = scout.sincronizza_rose_serie_a()

        if giocatori_api:
            # Indice a piu' chiavi: nome Fantacalcio, nome breve e solo cognome.
            # I nomi del listone sono abbreviati ("Martinez L."), quelli dell'API
            # completi ("Lautaro Martinez"): senza questo non si agganciano.
            indice, per_cognome = {}, {}
            for idx, riga in df_listone.iterrows():
                ruolo_riga = str(riga.get('R', '')).strip().upper()
                squadra_riga = str(riga.get('Squadra', '')).strip()
                for campo in ('Nome', 'Nome_Breve'):
                    chiave = normalize_str(riga.get(campo, ''))
                    if not chiave:
                        continue
                    indice.setdefault(chiave, idx)

                    parole_riga = chiave.split()
                    # Iniziali del nome proprio: in "Esposito Se." la parte dopo
                    # il cognome distingue Sebastiano da Francesco Pio.
                    iniziali = {p[0] for p in parole_riga[1:] if p}
                    # Si indicizzano TUTTE le parole lunghe, non solo la prima:
                    # i cognomi composti come "El Aynaoui" altrimenti si perdono.
                    for parola in parole_riga:
                        if len(parola) > 2:
                            per_cognome.setdefault(parola, []).append(
                                {'idx': idx, 'ruolo': ruolo_riga,
                                 'squadra': squadra_riga, 'iniziali': iniziali})

            aggiornati, non_trovati, ambigui = 0, [], 0
            candidati_nuovi = []
            for g in giocatori_api:
                norm = normalize_str(g['nome'])
                idx = indice.get(norm)

                if idx is None:
                    # Match per cognome SOLO se non ambiguo: "Lautaro Martinez"
                    # non deve finire su "Martinez Jo.", che e' un portiere.
                    parole_api = norm.split()
                    for parola in sorted(parole_api, key=len, reverse=True):
                        if len(parola) <= 2:
                            continue
                        candidati = per_cognome.get(parola, [])
                        if not candidati:
                            continue

                        if len({c['idx'] for c in candidati}) == 1:
                            # Cognome unico: si accetta anche se il ruolo differisce.
                            # Fantacalcio e API classificano diversamente (Orsolini
                            # e' centrocampista per uno, attaccante per l'altro).
                            idx = candidati[0]['idx']
                            break

                        # Omonimi: si restringe per iniziale del nome, poi squadra,
                        # poi ruolo. "S. Esposito" -> "Esposito Se.", non "Esposito Fr."
                        iniziali_api = {p[0] for p in parole_api if p != parola}
                        rimasti = [c for c in candidati
                                   if c['iniziali'] & iniziali_api] or candidati
                        if len({c['idx'] for c in rimasti}) > 1:
                            per_squadra = [c for c in rimasti if c['squadra'] == g['squadra']]
                            if per_squadra:
                                rimasti = per_squadra
                        if len({c['idx'] for c in rimasti}) > 1:
                            per_ruolo = [c for c in rimasti if c['ruolo'] == g['ruolo']]
                            if per_ruolo:
                                rimasti = per_ruolo

                        if len({c['idx'] for c in rimasti}) == 1:
                            idx = rimasti[0]['idx']
                            break
                        ambigui += 1
                        break

                if idx is not None:
                    # Collega l'id API al nome del listone: serve alle proiezioni
                    scout.associa(df_listone.loc[idx, 'Nome'], g.get('api_id'))
                    if g.get('api_id'):
                        id_api_riga[g['api_id']] = idx
                    if str(df_listone.loc[idx, 'Squadra']).strip() != g['squadra']:
                        df_listone.loc[idx, 'Squadra'] = g['squadra']
                        aggiornati += 1
                else:
                    non_trovati.append(g['nome'])
                    candidati_nuovi.append(g)

            # I giocatori assenti dalle quotazioni NON vengono aggiunti: all'asta
            # si comprano solo quelli del listone Fantacalcio.
            print(f"🔄 Squadra aggiornata per {aggiornati} giocatori.")
            print(f"ℹ️ {len(non_trovati)} giocatori dell'API non sono nel listone "
                  f"(non acquistabili all'asta, ignorati) | {ambigui} scartati per omonimia.")
            segnala_nuovi_arrivi(candidati_nuovi, scout)

            # Quante gare ha saltato per infortunio la stagione scorsa: e' il
            # dato che distingue chi si e' rotto da chi resta in panchina.
            df_listone['GareSaltate'] = 0
            df_listone['MotivoStop'] = ""
            try:
                storico = scout.storico_infortuni()
            except Exception as e:
                print(f"⚠️ Storico infortuni non recuperato: {e}")
                storico = {}
            for id_api, record in storico.items():
                idx = id_api_riga.get(id_api)
                if idx is None:
                    continue
                df_listone.loc[idx, 'GareSaltate'] = int(record.get('gare', 0))
                df_listone.loc[idx, 'MotivoStop'] = str(record.get('motivo', ''))[:60]
            if storico:
                print(f"🏥 Gare saltate agganciate a {sum(1 for i in storico if i in id_api_riga)} giocatori.")

            # Infortunati di oggi: una chiamata per tutto il campionato
            df_listone['Infortunio'] = ""
            df_listone['InfortunioTipo'] = ""
            df_listone['InfortunioDal'] = ""
            try:
                fermi = scout.infortuni_correnti()
            except Exception as e:
                print(f"⚠️ Infortuni non recuperati: {e}")
                fermi = {}

            # Da quando e' fermo: l'API non lo dice, lo memorizziamo noi al primo
            # avvistamento e lo teniamo in cache finche' l'infortunio non cambia.
            storico = scout.cache.setdefault('infortuni', {})
            oggi = datetime.date.today().isoformat()
            attivi = set()

            segnati = 0
            for id_api, info in fermi.items():
                idx = id_api_riga.get(id_api)
                chiave = str(id_api)
                attivi.add(chiave)
                motivo = info['motivo'] or info['tipo']

                precedente = storico.get(chiave)
                if precedente and precedente.get('motivo') == motivo:
                    dal = precedente['dal']
                else:
                    dal = oggi
                storico[chiave] = {'dal': dal, 'motivo': motivo}

                if idx is None:
                    continue

                df_listone.loc[idx, 'InfortunioTipo'] = info['tipo']
                df_listone.loc[idx, 'Infortunio'] = motivo
                df_listone.loc[idx, 'InfortunioDal'] = dal
                segnati += 1

            # Chi non e' piu' nell'elenco e' rientrato: si libera lo storico
            for chiave in list(storico):
                if chiave not in attivi:
                    storico.pop(chiave, None)
            if fermi:
                print(f"🚑 {segnati} indisponibili agganciati al listone.")
    except Exception as e:
        print(f"⚠️ Avviso API: {e}")

    # ------------------------------------------------------------------
    # INIEZIONE STATISTICHE + CALCOLO FVM
    # ------------------------------------------------------------------
    baseline = calcola_baseline_ruoli(stats_per_id)

    colonne_out = {c: [] for c in ['FVM', 'PvTot', 'SquadreStag', 'Tit', 'Min'] + COLONNE_STATS}
    conteggio = {'id': 0, 'nome': 0, 'nome_abbreviato': 0, 'scout': 0, 'nessuno': 0}

    for _, row in df_listone.iterrows():
        nome = str(row['Nome']).strip()
        ruolo = str(row['R']).strip()
        squadra = str(row['Squadra']).strip()

        # Qt.A e' la quotazione attuale: in un file pre-asta coincide con Qt.I,
        # a stagione in corso e' la piu' aggiornata. Prendere il massimo delle due
        # gonfiava chi era partito caro e si era svalutato (es. un lungodegente).
        qt_a = safe_float(row['Qt.A'])
        qt_i = safe_float(row['Qt.I'])
        best_qt = qt_a or qt_i or 1.0

        record, metodo = trova_stats(row['Id'], nome, ruolo, stats_per_id, stats_per_nome)

        valori = {c: 0 for c in COLONNE_STATS}
        if record is not None:
            conteggio[metodo] += 1
            for c in COLONNE_STATS:
                valori[c] = safe_float(record.get(c)) if c in COLONNE_DECIMALI else safe_int(record.get(c))

        pv = int(valori['Pv'])
        fm_storico = float(valori['Fm'])
        fm_grezza = fm_storico if fm_storico > 0 else None
        presenze_peso = pv

        # Nessuno storico in Serie A: proiezione dello scout (estero / nuovi arrivi)
        if fm_grezza is None:
            try:
                proiezione = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except Exception:
                proiezione = None
            if proiezione:
                conteggio['scout'] += 1
                fm_grezza = proiezione
                presenze_peso = K_SHRINK      # fiducia media: la proiezione pesa quanto la baseline
            elif record is None:
                conteggio['nessuno'] += 1

        base_ruolo = baseline.get(ruolo, 6.0)
        fm_per_fvm = fm_ponderata(fm_grezza, presenze_peso, base_ruolo)

        fvm_finale, fm_usata = calcola_fvm(best_qt, fm_per_fvm, ruolo, squadra,
                                           scout, nome, baseline)

        # Chi ha poche presenze in Serie A: si controlla quante ne ha in totale.
        presenze_totali, squadre_stagione = pv, 1
        da_titolare, minuti = 0, 0
        if 0 < pv < PRESENZE_SOSPETTE:
            try:
                extra = scout.presenze_stagione(nome)
            except Exception:
                extra = None
            if extra:
                presenze_totali = max(pv, extra['totali'])
                squadre_stagione = extra['squadre']
                da_titolare = extra.get('da_titolare', 0)
                minuti = extra.get('minuti', 0)

        colonne_out['PvTot'].append(int(presenze_totali))
        colonne_out['SquadreStag'].append(int(squadre_stagione))
        colonne_out['Tit'].append(int(da_titolare))
        colonne_out['Min'].append(int(minuti))
        colonne_out['FVM'].append(fvm_finale)
        for c in COLONNE_STATS:
            if c == 'Fm':
                colonne_out[c].append(round(fm_grezza, 2) if fm_grezza else 0.0)
            else:
                colonne_out[c].append(valori[c])

    for col, valori in colonne_out.items():
        df_listone[col] = valori

    for colonna in ('Infortunio', 'InfortunioTipo', 'InfortunioDal', 'MotivoStop'):
        if colonna not in df_listone.columns:
            df_listone[colonna] = ""
    if 'GareSaltate' not in df_listone.columns:
        df_listone['GareSaltate'] = 0
    df_listone['Aggiornato'] = datetime.date.today().isoformat()
    df_listone['Prezzo'] = calcola_prezzi(df_listone)
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
    print(f"💰 Prezzi calcolati su lega da {SQUADRE_LEGA} squadre e {BUDGET_LEGA} crediti.")
    print(f"✅ Lista_Finale_Master.csv rigenerato: {len(df_listone)} giocatori, "
          f"{con_stats} con statistiche reali.")


if __name__ == '__main__':
    main()

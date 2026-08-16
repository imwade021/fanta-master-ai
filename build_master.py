import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
import io
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

def normalize_and_tokenize(s):
    if not isinstance(s, str): return set()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return set(s.split())

def scarica_listone_aggiornato():
    print("📥 Download listone in corso...")
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone scaricato!")
            return True
    except Exception as e:
        print(f"⚠️ Download fallito: {e}")
    return False

def trova_fantamedia_reale(nome_cercato, df_stats):
    if df_stats.empty: return None
    tokens_cercato = normalize_and_tokenize(nome_cercato)
    if not tokens_cercato: return None

    # Ricerca Infallibile: Indipendente dall'ordine "Nome Cognome" o "Cognome Nome"
    for idx, row in df_stats.iterrows():
        tokens_stat = row.get('Tokens', set())
        if not tokens_stat: continue
        
        # Match Perfetto (es. [nico, paz] == [paz, nico])
        if tokens_cercato == tokens_stat:
            return row.get('Fm', None)
        
        # Match Parziale Sicuro (Se hanno almeno 2 parole uguali, o 1 parola lunga e unica)
        overlap = tokens_cercato.intersection(tokens_stat)
        if len(overlap) >= 2 or (len(overlap) == 1 and any(len(w) >= 5 for w in overlap)):
            return row.get('Fm', None)
            
    return None

def main():
    print("🚀 Avvio Master Engine - V DEFINITIVA (Match Infallibile e Pulizia Assoluta)...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
        # LETTURA BLINDATA DEL FILE
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            testo = f.read()
        separatore = ';' if ';' in testo else ','
        
        df_listone = pd.read_csv(io.StringIO(testo), header=None, sep=separatore, dtype=str, on_bad_lines='skip')
        
        # FORZATURA STRUTTURALE: Esattamente 19 colonne
        if len(df_listone.columns) > 19:
            df_listone = df_listone.iloc[:, :19]
        for i in range(len(df_listone.columns), 19):
            df_listone[i] = ""

        df_listone.columns = [
            'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
            'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
            'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
        ]

        # -------------------------------------------------------------
        # GHIGLIOTTINA 1: Elimina intestazioni e spazzatura HTML (Guida, Serie A, ecc)
        df_listone['R'] = df_listone['R'].astype(str).str.strip().str.upper()
        df_listone = df_listone[df_listone['R'].isin(['P', 'D', 'C', 'A'])]
        
        # GHIGLIOTTINA 2: L'ID deve essere un numero valido
        df_listone['Id_Num'] = pd.to_numeric(df_listone['Id'], errors='coerce')
        df_listone = df_listone.dropna(subset=['Id_Num'])
        df_listone = df_listone.drop(columns=['Id_Num'])
        # -------------------------------------------------------------
        
    except Exception as e:
        print(f"❌ Errore critico lettura CSV: {e}")
        return

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        # Prepara l'Excel per la ricerca intelligente
        df_stats['Tokens'] = df_stats['Nome'].apply(normalize_and_tokenize)
    except Exception:
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row.get('Nome', '')).replace('*', '').strip()
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        # PARSING QUOTAZIONI CORRETTO E PROTETTO DA SLITTAMENTI (>150 viene azzerato)
        qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_iniziale) or qt_iniziale > 150: qt_iniziale = 1.0
        
        qt_attuale = pd.to_numeric(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_attuale) or qt_attuale > 150: qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)
        
        # RICERCA FANTAMEDIA INFALLIBILE
        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)

        fm_val = None
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try:
                fm_val = float(str(fm_reale_raw).replace(',', '.'))
            except ValueError:
                pass

        if fm_val is None:
            try:
                fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fm_val is None: fm_val = 5.0
            except:
                fm_val = 5.0

        # ---------------------------------------------------------
        # IL MOTORE MATEMATICO (Curve perfette per il calcolo FVM)
        # ---------------------------------------------------------
        
        # 1. Valore basato sul Mercato (Quotazione Fantacalcio)
        fvm_da_qt = best_qt * 1.5
        
        # 2. Valore basato sul Campo (Curva Quadratica della FantaMedia)
        if fm_val > 5.5:
            # Formula letale: (7.3 di Nico Paz - 5.2)^2 * 12 = FVM ~52 (Perfetto per un Semi-Top)
            fvm_da_fm = (fm_val - 5.2) ** 2 * 12
        else:
            fvm_da_fm = max(1.0, best_qt)
            
        base_fvm = max(fvm_da_qt, fvm_da_fm)

        # Boost per giocatori rilevanti in Top Club
        if squadra in BIG_TEAMS and best_qt >= 8.0:
            base_fvm *= 1.15

        # Tetto massimo a 95.0, minimo a 1.0
        try:
            fvm_finale = round(min(95.0, max(1.0, float(base_fvm))), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna(0)
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv RIGENERATA. File Pulito e Calcoli Perfetti!")

if __name__ == '__main__':
    main()

import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']

def normalize_str(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.lower().split())

def scarica_listone_aggiornato():
    print("📥 Download dell'ultimo listone di mercato in corso...")
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            print("✅ Listone sorgente aggiornato con successo!")
            return True
    except Exception as e:
        print(f"⚠️ Download fallito, uso il file locale esistente: {e}")
    return False

def trova_fantamedia_reale(nome_cercato, df_stats):
    if df_stats.empty: return None
    norm_cercato = normalize_str(nome_cercato)
    
    match = df_stats[df_stats['Nome_Norm'] == norm_cercato]
    if not match.empty: return match.iloc[0].get('Fm', None)
    
    match = df_stats[df_stats['Nome_Norm'].apply(lambda x: norm_cercato in x or x in norm_cercato if isinstance(x, str) else False)]
    if not match.empty: return match.iloc[0].get('Fm', None)
    
    cognome = norm_cercato.split()[0] if norm_cercato else ""
    if len(cognome) > 2:
        match = df_stats[df_stats['Nome_Norm'].str.contains(cognome, regex=False, na=False)]
        if not match.empty: return match.iloc[0].get('Fm', None)
        
    return None

def main():
    print("🚀 Avvio Master Engine - V 3.0 (Intelligenza Analitica Pura)...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    try:
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            prima_riga = f.readline()
        separatore = ';' if ';' in prima_riga else ','
        df_listone = pd.read_csv("Lista-FantaAsta-Fantacalcio.csv", header=None, sep=separatore, on_bad_lines='skip')
        
        if len(df_listone.columns) > 19: df_listone = df_listone.iloc[:, :19]
        while len(df_listone.columns) < 19: df_listone[len(df_listone.columns)] = ""

        df_listone.columns = ['Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3']
    except Exception as e:
        print(f"❌ Errore critico: {e}")
        return

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
    except Exception:
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome_raw = str(row['Nome'])
        if nome_raw.lower() == 'nan' or nome_raw.strip() == '':
            fvm_calcolati.append(0)
            continue
            
        nome = nome_raw.replace('*', '').strip()
        ruolo = str(row['R']).replace('*', '').strip()
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        qt_iniziale = pd.to_numeric(str(row.get('Qt.I', 1)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_iniziale): qt_iniziale = 1.0
        qt_attuale = pd.to_numeric(str(row.get('Qt.A', qt_iniziale)).replace(',', '.'), errors='coerce')
        if pd.isna(qt_attuale): qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)
        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)

        # ---------------------------------------------------------
        # MOTORE 1: Curva del Mercato (Esponenziale su Quotazione)
        # Più costi, più il moltiplicatore sale.
        # Es: Qt=1 -> FVM 1.1 | Qt=15 -> FVM 27 | Qt=30 -> FVM 69
        # ---------------------------------------------------------
        fvm_da_qt = best_qt * (1.1 + (best_qt / 25.0))

        # ---------------------------------------------------------
        # MOTORE 2: Curva del Campo (Quadratica su FantaMedia)
        # Premia i top player ignorando in quale squadra giocano
        # ---------------------------------------------------------
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try:
                fm_val = float(str(fm_reale_raw).replace(',', '.'))
                # Formula quadratica: un 7.5 schizza in alto, un 6.0 resta basso
                fvm_da_fm = max(0, (fm_val - 5.5) ** 2 * 18) if fm_val > 5.5 else max(1.0, best_qt)
            except ValueError:
                fm_val = None
        else:
            fm_val = None

        if fm_val is None:
            try:
                fvm_proiettata = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fvm_proiettata is None: fvm_proiettata = 5.0
            except:
                fvm_proiettata = 5.0
            # Sulle proiezioni API andiamo leggermente più cauti (*14 invece di *18)
            fvm_da_fm = max(0, (fvm_proiettata - 5.5) ** 2 * 14) if fvm_proiettata > 5.5 else max(1.0, best_qt)

        # ---------------------------------------------------------
        # LA SINTESI: Si prende il dato che valorizza meglio il giocatore
        # ---------------------------------------------------------
        base_fvm = max(fvm_da_qt, fvm_da_fm)

        # Boost "Hype" Big Team: SI APPLICA SOLO SE SEI GIÀ UN GIOCATORE RILEVANTE (Qt >= 8)
        # I primavera e le riserve (Qt < 8) non prendono il boost!
        if squadra in BIG_TEAMS and best_qt >= 8.0:
            base_fvm *= 1.15

        try:
            fvm_finale = round(min(95.0, max(1.0, float(base_fvm))), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna(0)
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv generata con Intelligenza Analitica V3.0!")

if __name__ == '__main__':
    main()

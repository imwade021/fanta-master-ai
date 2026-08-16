import pandas as pd
import numpy as np
import os
import re
import unicodedata
from scout_engine import ScoutEngine

def normalize_str(s):
    if pd.isna(s): return ""
    s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return " ".join(s.split())

def main():
    print("🚀 Avvio Master Engine - ROOT MERGE & AI INCREMENT MODE")

    # =================================================================
    # 1. LE FONDAMENTA STORICHE (Excel)
    # =================================================================
    excel_file = "Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"
    df_stats = pd.DataFrame()
    if os.path.exists(excel_file):
        df_stats = pd.read_excel(excel_file, header=1)
        df_stats['Nome_Norm'] = df_stats['Nome'].apply(normalize_str)
        print(f"✅ Storico Excel caricato.")
    else:
        print(f"⚠️ Attenzione: File storico {excel_file} non trovato.")

    # =================================================================
    # 2. IL LISTONE AGGIORNATO (CSV) - La nostra struttura portante
    # =================================================================
    csv_file = "Lista-FantaAsta-Fantacalcio.csv"
    if not os.path.exists(csv_file):
        print(f"❌ Errore fatale: {csv_file} mancante.")
        return

    # Leggiamo il CSV in modo sicuro, mantenendo tutto il contenuto valido
    with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
        prima_riga = f.readline()
    sep = ';' if ';' in prima_riga else ','

    df_listone = pd.read_csv(csv_file, sep=sep, header=None, dtype=str, on_bad_lines='skip')
    
    # Assicuriamo la struttura a 19 colonne
    if len(df_listone.columns) > 19: 
        df_listone = df_listone.iloc[:, :19]
    while len(df_listone.columns) < 19: 
        df_listone[len(df_listone.columns)] = ""

    df_listone.columns = [
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ]

    # Teniamo solo le righe dei giocatori reali (chi ha un ruolo) senza distruggere i dati
    df_listone['R'] = df_listone['R'].astype(str).str.strip().str.upper()
    df_listone = df_listone[df_listone['R'].isin(['P', 'D', 'C', 'A'])]
    print(f"✅ Struttura Listone caricata: {len(df_listone)} giocatori pronti.")

    # =================================================================
    # 3. MERGE & IMPLEMENTAZIONE IA SUI NUOVI ARRIVI
    # =================================================================
    scout = ScoutEngine()
    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome']).strip()
        ruolo = str(row['R']).strip()
        squadra = str(row['Squadra']).strip()

        # Preleviamo le quotazioni ufficiali (la nostra radice)
        try: qt_i = float(str(row['Qt.I']).replace(',', '.'))
        except: qt_i = 1.0
        try: qt_a = float(str(row['Qt.A']).replace(',', '.'))
        except: qt_a = qt_i
        best_qt = max(qt_i, qt_a)

        fm_val = None
        norm_nome = normalize_str(nome)

        # FASE A: Cerca nello storico ufficiale (Non buttiamo via niente!)
        if not df_stats.empty:
            match = df_stats[df_stats['Nome_Norm'] == norm_nome]
            if match.empty:
                # Ricerca flessibile per cognome se il nome esatto non matcha
                match = df_stats[df_stats['Nome_Norm'].str.contains(norm_nome.split()[0], na=False, regex=False) if norm_nome else False]
            
            if not match.empty:
                try: fm_val = float(str(match.iloc[0]['Fm']).replace(',', '.'))
                except: pass

        # FASE B: IL NUOVO ARRIVO - L'Intelligenza Artificiale entra in gioco solo qui!
        if fm_val is None or fm_val == 0.0:
            print(f"🤖 Intervento IA per Nuovo Arrivo: {nome} ({squadra})")
            try: 
                fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except: 
                fm_val = None

        # Paracadute finale se non ci sono dati da nessuna parte
        if fm_val is None: 
            fm_val = 6.0

        # =================================================================
        # 4. CALCOLO VALORE FVM (Equilibrato e Lineare)
        # =================================================================
        if ruolo == 'A':
            base_fvm = best_qt * 1.5 + max(0, (fm_val - 6.0) * 35)
        elif ruolo == 'C':
            base_fvm = best_qt * 1.3 + max(0, (fm_val - 5.5) * 25)
        elif ruolo == 'D':
            base_fvm = best_qt * 1.2 + max(0, (fm_val - 5.5) * 15)
        elif ruolo == 'P':
            base_fvm = best_qt * 1.2 + max(0, (fm_val - 5.0) * 15)
        else:
            base_fvm = best_qt * 1.2

        if squadra in ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna']:
            base_fvm *= 1.15

        fvm_finale = round(min(500.0, max(1.0, float(base_fvm))), 1)
        fvm_calcolati.append(fvm_finale)

    # =================================================================
    # 5. SALVATAGGIO NEL FILE MASTER
    # =================================================================
    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Generazione completata! Lista_Finale_Master.csv è aggiornato con lo storico e i nuovi arrivi.")

if __name__ == '__main__':
    main()

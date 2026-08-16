import pandas as pd
import numpy as np
import os
import re
import unicodedata
from scout_engine import ScoutEngine

BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna']

def normalize_and_tokenize(s):
    if not isinstance(s, str): return set()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return set(s.split())

def main():
    print("🚀 Avvio Master Engine - LOCAL MODE (Nessun download web)")

    # 1. CARICAMENTO QUOTAZIONI EXCEL (Legge il file locale)
    excel_file = "Quotazioni_Fantacalcio_Stagione_2025_26.xlsx"
    df_stats = pd.DataFrame()
    if os.path.exists(excel_file):
        print(f"📄 Trovato file statistiche: {excel_file}")
        try:
            df_stats = pd.read_excel(excel_file, header=1)
            if 'Nome' in df_stats.columns:
                df_stats['Tokens'] = df_stats['Nome'].apply(normalize_and_tokenize)
        except Exception as e:
            print(f"⚠️ Errore lettura {excel_file}: {e}")
    else:
        print(f"❌ File {excel_file} NON TROVATO LOCALMENTE.")

    # 2. CARICAMENTO LISTONE CSV SORGENTE (Legge il file locale)
    csv_file = "Lista-FantaAsta-Fantacalcio.csv"
    if not os.path.exists(csv_file):
        print(f"❌ File {csv_file} NON TROVATO.")
        return

    print(f"📄 Lettura {csv_file}...")
    try:
        with open(csv_file, "r", encoding="utf-8", errors="ignore") as f:
            testo = f.read()
        sep = ';' if ';' in testo else ','
        lines = testo.split('\n')
    except Exception as e:
        print(f"❌ Errore lettura {csv_file}: {e}")
        return

    valid_data = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean: continue
        parts = line_clean.split(sep)
        
        # Ignora righe malformate
        if len(parts) < 10: continue
        
        id_str = parts[0].strip()
        ruolo = parts[3].strip().upper()
        
        # Filtro d'acciaio: se non ha un ID numerico e un Ruolo valido, non è un giocatore. Addio "Serie A" e "Guida".
        if not id_str.isdigit(): continue
        if ruolo not in ['P', 'D', 'C', 'A']: continue
        
        row_data = parts[:19]
        while len(row_data) < 19: row_data.append("")
        valid_data.append(row_data)

    df_listone = pd.DataFrame(valid_data, columns=[
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ])

    # 3. CALCOLO FVM (Matematica lineare e stabile)
    scout = ScoutEngine()
    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome'])
        ruolo = str(row['R'])
        squadra = str(row['Squadra']).strip()

        # Gestione quotazioni sballate
        try: qt_i = float(str(row['Qt.I']).replace(',', '.'))
        except: qt_i = 1.0
        try: qt_a = float(str(row['Qt.A']).replace(',', '.'))
        except: qt_a = qt_i

        best_qt = max(qt_i, qt_a)
        if best_qt > 60: best_qt = 1.0 # Sistema il bug di Carnesecchi a 94

        # Trova la FantaMedia nel file locale
        fm_val = None
        if not df_stats.empty:
            t_cerca = normalize_and_tokenize(nome)
            for _, srow in df_stats.iterrows():
                t_stat = srow.get('Tokens', set())
                if t_cerca == t_stat or len(t_cerca.intersection(t_stat)) >= 2:
                    try: 
                        fm_val = float(str(srow['Fm']).replace(',', '.'))
                    except: pass
                    break
        
        # Se non ha FantaMedia, interroga lo ScoutEngine o assegna base
        if fm_val is None:
            try: fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except: fm_val = None
            if fm_val is None: fm_val = 6.0

        # Formule lineari: crescono in modo proporzionale a Quotazione e FantaMedia
        if ruolo == 'A':
            base_fvm = best_qt * 1.8 + max(0, (fm_val - 6.0) * 35)
        elif ruolo == 'C':
            base_fvm = best_qt * 1.5 + max(0, (fm_val - 5.5) * 25)
        elif ruolo == 'D':
            base_fvm = best_qt * 1.3 + max(0, (fm_val - 5.5) * 15)
        elif ruolo == 'P':
            base_fvm = best_qt * 1.2 + max(0, (fm_val - 5.0) * 15)
        else:
            base_fvm = best_qt * 1.5

        # Boost per le Big
        if squadra in BIG_TEAMS:
            base_fvm *= 1.15

        # FVM finale arrotondato
        fvm_finale = round(min(500.0, max(1.0, float(base_fvm))), 1)
        fvm_calcolati.append(fvm_finale)

    # 4. SALVATAGGIO
    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Elaborazione completata, Lista_Finale_Master.csv generato in locale!")

if __name__ == '__main__':
    main()

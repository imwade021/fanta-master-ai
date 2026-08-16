import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna', 'Como']
GARBAGE = ['guida', 'asta', 'rose', 'scheda', 'serie a', 'fantacalcio', 'news', 'home', '>>']

def normalize_and_tokenize(s):
    if not isinstance(s, str): return set()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return set(s.split())

def main():
    print("🚀 Avvio Master Engine - RICERCA DINAMICA E CURVE ATTIVE...")
    
    # -----------------------------------------------------------------
    # 1. TROVA IL FILE STATISTICHE DINAMICAMENTE (Addio Bug dei Cloni)
    # -----------------------------------------------------------------
    stats_file = None
    for f in os.listdir('.'):
        if ('statistiche' in f.lower() or 'quotazioni' in f.lower()) and (f.endswith('.xlsx') or f.endswith('.xls') or f.endswith('.csv')):
            stats_file = f
            break
    
    df_stats = pd.DataFrame()
    if stats_file:
        print(f"📄 Trovato file statistiche: {stats_file}")
        try:
            if stats_file.endswith('.csv'):
                df_stats = pd.read_csv(stats_file)
            else:
                df_stats = pd.read_excel(stats_file, header=1)
            
            if 'Nome' in df_stats.columns:
                df_stats['Tokens'] = df_stats['Nome'].apply(normalize_and_tokenize)
        except Exception as e:
            print(f"⚠️ Errore caricamento statistiche: {e}")

    # -----------------------------------------------------------------
    # 2. DOWNLOAD E PULIZIA BRUTALE DEL CSV SORGENTE
    # -----------------------------------------------------------------
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        testo = res.text
    except Exception as e:
        print(f"❌ Errore download Listone: {e}")
        return

    sep = ';' if ';' in testo else ','
    lines = testo.split('\n')
    
    valid_data = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean: continue
        parts = line_clean.split(sep)
        
        # Scarta righe palesemente rotte (es. meno di 10 colonne)
        if len(parts) < 10: continue
        
        id_str = parts[0].strip()
        nome_raw = parts[2].strip()
        ruolo = parts[3].strip().upper()
        squadra_raw = parts[9].strip()
        
        # FILTRO 1: L'ID deve essere un numero
        if not id_str.isdigit(): continue
        # FILTRO 2: Il Ruolo deve esistere
        if ruolo not in ['P', 'D', 'C', 'A']: continue
        
        # FILTRO 3: Anti-Spazzatura Web
        nome_lower = nome_raw.lower()
        if any(char.isdigit() for char in nome_raw): continue
        if any(g in nome_lower for g in GARBAGE): continue
        if nome_lower == squadra_raw.lower(): continue
        
        row_data = parts[:19]
        while len(row_data) < 19: row_data.append("")
        valid_data.append(row_data)
        
    df_listone = pd.DataFrame(valid_data, columns=[
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ])

    # -----------------------------------------------------------------
    # 3. MOTORE MATEMATICO (Curve Esponenziali e Max 450 FVM)
    # -----------------------------------------------------------------
    scout = ScoutEngine()
    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row['Nome'])
        ruolo = str(row['R'])
        squadra = str(row['Squadra'])
        
        # Correzione anomalie di Quotazione (es. Carnesecchi 94)
        try: qt_iniziale = float(str(row['Qt.I']).replace(',', '.'))
        except: qt_iniziale = 1.0
        try: qt_attuale = float(str(row['Qt.A']).replace(',', '.'))
        except: qt_attuale = qt_iniziale
        
        best_qt = max(qt_iniziale, qt_attuale)
        if best_qt > 60: best_qt = 1.0 # Nessun giocatore parte con 60 crediti, è un errore di Fantacalcio
        
        # Trova la VERA FantaMedia
        fm_val = None
        if not df_stats.empty:
            tokens_cercato = normalize_and_tokenize(nome)
            for _, srow in df_stats.iterrows():
                t_stat = srow.get('Tokens', set())
                # Se c'è un incrocio di almeno 2 parole o una parola lunga (es. "Carnesecchi")
                if tokens_cercato == t_stat or len(tokens_cercato.intersection(t_stat)) >= 2 or (len(tokens_cercato.intersection(t_stat)) == 1 and any(len(w) >= 5 for w in tokens_cercato.intersection(t_stat))):
                    try: 
                        fm_val = float(str(srow['Fm']).replace(',', '.'))
                    except: pass
                    break
        
        # Se non ha FantaMedia italiana, chiediamo all'intelligenza artificiale
        if fm_val is None:
            try: fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
            except: pass
            if fm_val is None: fm_val = 5.0

        # Calcolo a curve differenziato per ruolo
        base_fvm = max(1.0, best_qt)
        if fm_val > 5.5:
            diff = fm_val - 5.5
            if ruolo == 'A': base_fvm = (diff ** 3) * 18
            elif ruolo == 'C': base_fvm = (diff ** 3) * 14
            elif ruolo == 'D': base_fvm = (diff ** 3) * 10
            elif ruolo == 'P': base_fvm = (diff ** 3) * 15
        
        if squadra in BIG_TEAMS:
            base_fvm *= 1.25
            
        try: fvm_finale = round(min(450.0, max(1.0, float(base_fvm))), 1)
        except: fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ Lista_Finale_Master.csv rigenerata con successo e matematica ripristinata!")

if __name__ == '__main__':
    main()

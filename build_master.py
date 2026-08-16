import pandas as pd
import numpy as np
import requests
import os
import re
import unicodedata
import io
from scout_engine import ScoutEngine

LISTONE_URL = "https://raw.githubusercontent.com/imwade021/fanta-data-bridge/main/Lista-FantaAsta-Fantacalcio.csv"
BIG_TEAMS = ['Inter', 'Milan', 'Juventus', 'Napoli', 'Roma', 'Atalanta', 'Lazio', 'Fiorentina', 'Bologna']

# Parole "tossiche" per ripulire i menu del sito sfuggiti allo scraping
GARBAGE_WORDS = ['guida', 'asta', 'rose', 'scheda', 'serie a', 'fantacalcio', '>>', 'news', 'home']

def normalize_and_tokenize(s):
    if not isinstance(s, str): return set()
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return set(s.split())

def scarica_listone_aggiornato():
    try:
        res = requests.get(LISTONE_URL, timeout=15)
        if res.status_code == 200:
            with open("Lista-FantaAsta-Fantacalcio.csv", "wb") as f:
                f.write(res.content)
            return True
    except: pass
    return False

def trova_fantamedia_reale(nome_cercato, df_stats):
    if df_stats.empty: return None
    tokens_cercato = normalize_and_tokenize(nome_cercato)
    if not tokens_cercato: return None

    for idx, row in df_stats.iterrows():
        tokens_stat = row.get('Tokens', set())
        if not tokens_stat: continue
        if tokens_cercato == tokens_stat:
            return row.get('Fm', None)
        overlap = tokens_cercato.intersection(tokens_stat)
        if len(overlap) >= 2 or (len(overlap) == 1 and any(len(w) >= 5 for w in overlap)):
            return row.get('Fm', None)
    return None

def main():
    print("🚀 Avvio Master Engine - CURVE ESPONENZIALI E FILTRO BLINDATO...")
    
    scarica_listone_aggiornato()
    scout = ScoutEngine()
    
    valid_data = []
    try:
        with open("Lista-FantaAsta-Fantacalcio.csv", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        header_found = False
        sep = ','
        
        for line in lines:
            line_clean = line.strip()
            if not line_clean: continue
            
            if not header_found:
                if 'nome' in line_clean.lower() and 'squadra' in line_clean.lower():
                    header_found = True
                    sep = ';' if ';' in line_clean else ','
                continue
                
            parts = line_clean.split(sep)
            if len(parts) >= 10:
                # -------------------------------------------------------------
                # FILTRO 1: L'ID DEVE ESSERE UN NUMERO (Ghigliottina per titoli e righe vuote)
                try: int(parts[0].strip())
                except ValueError: continue

                # FILTRO 2: Ruolo Valido
                ruolo = parts[3].strip().upper()
                if ruolo not in ['P', 'D', 'C', 'A']: continue
                
                # FILTRO 3: Scudo contro i finti giocatori (Menu, Numeri, Squadre)
                nome_raw = parts[2].strip()
                nome_lower = nome_raw.lower()
                squadra_raw = parts[9].strip()
                
                if any(char.isdigit() for char in nome_raw): continue
                if nome_lower == squadra_raw.lower(): continue
                if any(g in nome_lower for g in GARBAGE_WORDS): continue
                # -------------------------------------------------------------
                
                row_data = parts[:19]
                while len(row_data) < 19: row_data.append("")
                valid_data.append(row_data)
                
    except Exception as e:
        print(f"❌ Errore lettura: {e}")
        return

    df_listone = pd.DataFrame(valid_data, columns=[
        'Id', 'Nome_Breve', 'Nome', 'R', 'Ruolo_Esteso', 'Qt.A', 'Qt.I', 
        'Qt.M', 'Diff.M', 'Squadra', 'FVM', 'FVM.M', 'Piede', 'Nazionalita', 
        'DataNascita', 'PhotoURL', 'Extra1', 'Extra2', 'Extra3'
    ])

    try:
        df_stats = pd.read_excel("Quotazioni_Fantacalcio_Stagione_2025_26.xlsx", header=1)
        df_stats['Tokens'] = df_stats['Nome'].apply(normalize_and_tokenize)
    except:
        df_stats = pd.DataFrame()

    fvm_calcolati = []

    for idx, row in df_listone.iterrows():
        nome = str(row.get('Nome', '')).replace('*', '').strip()
        ruolo = str(row['R'])
        squadra = str(row.get('Squadra', '')).replace('*', '').strip()
        
        fm_reale_raw = trova_fantamedia_reale(nome, df_stats)
        fm_val = None
        
        if fm_reale_raw is not None and str(fm_reale_raw).strip() != '':
            try: fm_val = float(str(fm_reale_raw).replace(',', '.'))
            except: pass

        if fm_val is None:
            try:
                fm_val = scout.calcola_fantamedia_proiettata(nome, ruolo)
                if fm_val is None: fm_val = 5.0
            except: fm_val = 5.0

        # -------------------------------------------------------------
        # LE CURVE ESPONENZIALI (Ignoriamo le quotazioni rotte)
        # -------------------------------------------------------------
        base_fvm = 1.0
        
        if fm_val > 5.5:
            diff = fm_val - 5.5
            
            # Formule letali e personalizzate per ruolo! 
            if ruolo == 'A':
                base_fvm = (diff ** 3) * 18   # Es: Lautaro (8.5 FM) -> diff 3.0 -> 3^3 * 18 = 486 FVM
            elif ruolo == 'C':
                base_fvm = (diff ** 3) * 14   # Es: Calhanoglu (7.5 FM) -> diff 2.0 -> 2^3 * 14 = 112 FVM
            elif ruolo == 'D':
                base_fvm = (diff ** 3) * 10   # Difensori crescono più lentamente
            elif ruolo == 'P':
                base_fvm = (diff ** 3) * 15   # Portieri top costano parecchio
        
        # Premio extra per chi gioca nelle squadre di cartello (garanzia)
        if squadra in BIG_TEAMS:
            base_fvm *= 1.25
            
        # NESSUN TETTO 95.0! Blocchiamo a 450 solo per evitare numeri astronomici (es. chi ha 1 presenza con 10 di media)
        try:
            fvm_finale = round(min(450.0, max(1.0, float(base_fvm))), 1)
        except:
            fvm_finale = 1.0

        fvm_calcolati.append(fvm_finale)

    df_listone['FVM'] = fvm_calcolati
    df_listone = df_listone.fillna(0)
    df_listone.to_csv("Lista_Finale_Master.csv", sep=';', index=False)
    print("✅ File CSV Generato: Filtri attivi e limiti rimossi (Max FVM 450)!")

if __name__ == '__main__':
    main()

import os
import requests
import time
import urllib.parse

class ScoutEngine:
    def __init__(self):
        # Livello di sicurezza: Recuperiamo la chiave dalla cassaforte di GitHub
        self.api_key = os.environ.get('API_FOOTBALL_KEY')
        
        # Header per l'API Ufficiale
        self.api_headers = {
            'x-apisports-key': self.api_key if self.api_key else ''
        }
        
        # Header per le ricerche web d'emergenza (Wikipedia)
        self.web_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'
        }

        self.coefficienti_campionati = {
            'Premier League': 1.0, 'La Liga': 0.95, 'Bundesliga': 0.90, 'Ligue 1': 0.85,
            'Serie B': 0.80, 'Eredivisie': 0.75, 'Primeira Liga': 0.75, 'Brasileirao': 0.70,
            'Championship': 0.70, 'Sconosciuto': 0.65
        }

    def cerca_api_ufficiale(self, nome_giocatore):
        """Livello 1: Ricerca chirurgica nel database di API-Football"""
        if not self.api_key:
            return None
            
        print(f"   [+] Livello 1: Interrogo API-Football per {nome_giocatore}...")
        try:
            url = "https://v3.football.api-sports.io/players"
            # Cerchiamo i dati dell'ultima stagione conclusa (2025/2026 -> usiamo 2025 per i campionati invernali)
            params = {'search': nome_giocatore, 'season': 2025}
            response = requests.get(url, headers=self.api_headers, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results', 0) > 0:
                    # Trovato! Estraiamo le statistiche
                    stats = data['response'][0]['statistics'][0]
                    games = stats['games']['appearences'] or 0
                    goals = stats['goals']['total'] or 0
                    assists = stats['goals']['assists'] or 0
                    yellows = stats['cards']['yellow'] or 0
                    league = stats['league']['name'] or 'Sconosciuto'
                    
                    if games > 0:
                        print("   [✓] Dati API recuperati con successo!")
                        return {
                            'presenze': games, 'gol': goals, 'assist': assists, 
                            'ammonizioni': yellows, 'campionato_origine': league
                        }
        except Exception as e:
            print(f"   [!] Errore API: {e}")
        return None

    def cerca_euristica_emergenza(self, nome_giocatore, ruolo):
        """Livello di Sopravvivenza: Generazione dati logici garantita al 100%"""
        print(f"   [-] Livello d'emergenza attivato per {nome_giocatore} (Ruolo: {ruolo})")
        
        # Assegniamo statistiche base credibili a seconda del ruolo in campo
        if ruolo == 'A':
            return {'presenze': 20, 'gol': 6, 'assist': 2, 'ammonizioni': 2, 'campionato_origine': 'Sconosciuto'}
        elif ruolo == 'C' or ruolo == 'T':
            return {'presenze': 25, 'gol': 3, 'assist': 4, 'ammonizioni': 5, 'campionato_origine': 'Sconosciuto'}
        elif ruolo == 'D' or ruolo == 'E' or ruolo == 'B':
            return {'presenze': 25, 'gol': 1, 'assist': 1, 'ammonizioni': 7, 'campionato_origine': 'Sconosciuto'}
        else:
            return {'presenze': 30, 'gol': 0, 'assist': 0, 'ammonizioni': 0, 'campionato_origine': 'Sconosciuto'}

    def estrai_dati(self, nome_giocatore, ruolo):
        # Tenta il Livello 1 (API)
        dati = self.cerca_api_ufficiale(nome_giocatore)
        
        # Se fallisce, passa al Livello di Sopravvivenza
        if non dati:
            dati = self.cerca_euristica_emergenza(nome_giocatore, ruolo)
            
        time.sleep(0.2) # Pausa leggerissima
        return dati

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        print(f"\n🕵️ Analisi su {nome_giocatore}...")
        dati = self.estrai_dati(nome_giocatore, ruolo)
        
        presenze = dati['presenze']
        gol = dati['gol']
        assist = dati['assist']
        malus = dati['ammonizioni'] * 0.5
        campionato = dati['campionato_origine']
        
        coeff = self.coefficienti_campionati.get(campionato, 0.65)
        
        if ruolo in ['A', 'C', 'T', 'D', 'E', 'B']:
            bonus_totale = (gol * 3) + (assist * 1)
        else: 
            bonus_totale = 0 
            
        bonus_adattato = bonus_totale * coeff
        voto_base_estero = 6.0 if presenze > 15 else 5.8
        
        fantamedia_proiettata = voto_base_estero + (bonus_adattato / presenze) - (malus / presenze)
        fantamedia_proiettata = max(5.0, min(8.5, fantamedia_proiettata))
        
        print(f"   => P-FM Calcolata: {round(fantamedia_proiettata, 2)} (da {campionato})")
        return round(fantamedia_proiettata, 2)

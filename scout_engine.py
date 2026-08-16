import os
import requests
import re
import unicodedata

class ScoutEngine:
    def __init__(self):
        # Intercetta il secret sotto qualsiasi nome sia stato salvato
        self.api_key = (
            os.getenv("FOOTBALL_API_KEY") or 
            os.getenv("API_FOOTBALL_KEY") or 
            os.getenv("RAPIDAPI_KEY")
        )
        self.base_url = "https://v3.football.api-sports.io"
        
        # Mappatura ID Squadre Serie A su API-Football
        self.serie_a_teams = {
            'Inter': 505, 'Milan': 489, 'Juventus': 496, 'Napoli': 492,
            'Roma': 497, 'Atalanta': 499, 'Lazio': 487, 'Fiorentina': 502,
            'Bologna': 500, 'Torino': 503, 'Udinese': 494, 'Genoa': 495,
            'Verona': 504, 'Cagliari': 490, 'Empoli': 511, 'Lecce': 867,
            'Monza': 1579, 'Como': 1020, 'Parma': 523, 'Venezia': 517
        }

    def _get_headers(self):
        return {
            'x-apisports-key': self.api_key,
            'x-rapidapi-key': self.api_key
        }

    def sincronizza_rose_serie_a(self):
        """Scansiona le rose ufficiali via API e rileva i nuovi acquisti di mercato"""
        if not self.api_key:
            print("⚠️ FOOTBALL_API_KEY non trovata nei Secrets di GitHub. Sincronizzazione rose saltata.")
            return []

        nuovi_giocatori = []
        print(f"📡 Connessione ad API-Football in corso per la scansione delle rose...")

        for squadra, team_id in self.serie_a_teams.items():
            try:
                url = f"{self.base_url}/players/squads?team={team_id}"
                res = requests.get(url, headers=self._get_headers(), timeout=8)
                
                if res.status_code == 200:
                    data = res.json()
                    players = data.get('response', [])[0].get('players', []) if data.get('response') else []
                    
                    for p in players:
                        nome_p = p.get('name')
                        pos_p = p.get('position', 'Midfielder')
                        
                        ruolo_fanta = 'C'
                        if pos_p == 'Goalkeeper': ruolo_fanta = 'P'
                        elif pos_p == 'Defender': ruolo_fanta = 'D'
                        elif pos_p == 'Attacker': ruolo_fanta = 'A'

                        if nome_p:
                            nuovi_giocatori.append({
                                'nome': nome_p,
                                'ruolo': ruolo_fanta,
                                'squadra': squadra,
                                'quotazione_base': 10
                            })
            except Exception:
                continue

        print(f"✅ Sincronizzazione completata: rilevati {len(nuovi_giocatori)} calciatori via API!")
        return nuovi_giocatori

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        """Recupera lo storico estero/recente per proiettare la FantaMedia dei nuovi arrivi"""
        if not self.api_key:
            return 5.8

        try:
            url = f"{self.base_url}/players?search={nome_giocatore}"
            res = requests.get(url, headers=self._get_headers(), timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data.get('response'):
                    stats = data['response'][0].get('statistics', [])[0]
                    goals = stats.get('goals', {}).get('total') or 0
                    assists = stats.get('goals', {}).get('assists') or 0
                    apps = stats.get('games', {}).get('appearences') or 1
                    
                    base_mv = 6.0
                    bonus = (goals * 3 + assists * 1) / max(1, apps)
                    return round(base_mv + bonus, 2)
        except Exception:
            pass

        return 5.8

import os
import re
import json
import unicodedata
import requests

from fanta_engine import FantaEngine

LEAGUE_ID_SERIE_A = 135
SEASON = int(os.getenv("FANTA_SEASON", "2025"))          # 2025 = stagione 2025/26
MAX_LOOKUP = int(os.getenv("FANTA_MAX_LOOKUP", "80"))     # tetto chiamate /players per run
CACHE_FILE = "scout_cache.json"

# Fallback usato solo se /teams non risponde. Gli Id API sono stabili nel tempo.
FALLBACK_TEAMS = {
    'Inter': 505, 'Milan': 489, 'Juventus': 496, 'Napoli': 492,
    'Roma': 497, 'Atalanta': 499, 'Lazio': 487, 'Fiorentina': 502,
    'Bologna': 500, 'Torino': 503, 'Udinese': 494, 'Genoa': 495,
    'Verona': 504, 'Cagliari': 490, 'Lecce': 867, 'Como': 1020,
    'Parma': 523
}

# Nomi API -> nomi usati nel listone Fantacalcio
ALIAS_SQUADRE = {
    'hellas verona': 'Verona',
    'ac milan': 'Milan',
    'as roma': 'Roma',
    'ssc napoli': 'Napoli',
    'inter': 'Inter',
    'fc internazionale': 'Inter',
    'us lecce': 'Lecce',
    'us cremonese': 'Cremonese',
    'ac pisa': 'Pisa',
    'us sassuolo': 'Sassuolo',
}


def normalize_str(s):
    if not isinstance(s, str):
        s = str(s or "")
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = re.sub(r"[^\w\s]", "", s).lower()
    return " ".join(s.split())


def nome_squadra_listone(nome_api):
    chiave = normalize_str(nome_api)
    if chiave in ALIAS_SQUADRE:
        return ALIAS_SQUADRE[chiave]
    return str(nome_api).strip()


class ScoutEngine:
    def __init__(self):
        self.api_key = (
            os.getenv("FOOTBALL_API_KEY") or
            os.getenv("API_FOOTBALL_KEY") or
            os.getenv("RAPIDAPI_KEY")
        )
        self.base_url = "https://v3.football.api-sports.io"
        self.engine = FantaEngine()

        self.serie_a_teams = {}          # nome squadra -> team id
        self.mappa_api_id = {}           # nome giocatore normalizzato -> player id API
        self.chiamate_players = 0
        self.cache = self._carica_cache()

    # ------------------------------------------------------------------
    # CACHE (risparmia quota: il piano free ha ~100 chiamate/giorno)
    # ------------------------------------------------------------------
    def _carica_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"stats": {}}

    def salva_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"⚠️ Impossibile salvare la cache: {e}")

    # ------------------------------------------------------------------
    # CHIAMATA BASE
    # ------------------------------------------------------------------
    def _get(self, endpoint, params, timeout=10):
        """Ritorna la lista 'response' oppure [] loggando l'errore vero dell'API."""
        if not self.api_key:
            return []
        try:
            res = requests.get(
                f"{self.base_url}/{endpoint}",
                headers={'x-apisports-key': self.api_key},
                params=params,
                timeout=timeout
            )
        except Exception as e:
            print(f"⚠️ Errore rete su /{endpoint}: {e}")
            return []

        if res.status_code != 200:
            print(f"⚠️ /{endpoint} ha risposto HTTP {res.status_code}")
            return []

        try:
            data = res.json()
        except Exception:
            print(f"⚠️ /{endpoint}: risposta non JSON")
            return []

        # L'API risponde 200 anche quando i parametri sono sbagliati: l'errore sta qui.
        errori = data.get('errors')
        if errori and not isinstance(errori, list):
            print(f"⚠️ /{endpoint} errore API: {errori}")
            return []

        return data.get('response', []) or []

    # ------------------------------------------------------------------
    # SQUADRE DELLA STAGIONE CORRENTE (niente lista hardcoded)
    # ------------------------------------------------------------------
    def carica_squadre_serie_a(self):
        risposta = self._get("teams", {'league': LEAGUE_ID_SERIE_A, 'season': SEASON})
        squadre = {}
        for item in risposta:
            team = item.get('team', {})
            if team.get('id') and team.get('name'):
                squadre[nome_squadra_listone(team['name'])] = team['id']

        if squadre:
            print(f"✅ Squadre Serie A {SEASON}/{str(SEASON + 1)[-2:]}: {len(squadre)} rilevate dall'API.")
        else:
            squadre = dict(FALLBACK_TEAMS)
            print(f"⚠️ /teams non disponibile: uso la lista di fallback ({len(squadre)} squadre, potenzialmente incompleta).")

        self.serie_a_teams = squadre
        return squadre

    # ------------------------------------------------------------------
    # ROSE
    # ------------------------------------------------------------------
    def sincronizza_rose_serie_a(self):
        if not self.api_key:
            print("⚠️ API Key non trovata. Sincronizzazione rose saltata.")
            return []

        if not self.serie_a_teams:
            self.carica_squadre_serie_a()

        nuovi_giocatori = []
        squadre_vuote = []
        print("📡 Connessione ad API-Football per la scansione rose...")

        for squadra, team_id in self.serie_a_teams.items():
            risposta = self._get("players/squads", {'team': team_id})
            players = risposta[0].get('players', []) if risposta else []

            if not players:
                squadre_vuote.append(squadra)
                continue

            for p in players:
                nome_p = p.get('name')
                if not nome_p:
                    continue

                pos_p = p.get('position', 'Midfielder')
                ruolo_fanta = {'Goalkeeper': 'P', 'Defender': 'D', 'Attacker': 'A'}.get(pos_p, 'C')

                if p.get('id'):
                    self.mappa_api_id[normalize_str(nome_p)] = p['id']

                nuovi_giocatori.append({
                    'nome': nome_p,
                    'ruolo': ruolo_fanta,
                    'squadra': squadra,
                    'api_id': p.get('id'),
                    'quotazione_base': 1
                })

        if squadre_vuote:
            print(f"⚠️ Rosa vuota per: {', '.join(squadre_vuote)}")
        print(f"✅ Sincronizzazione completata: {len(nuovi_giocatori)} giocatori rilevati "
              f"su {len(self.serie_a_teams) - len(squadre_vuote)} squadre.")
        return nuovi_giocatori

    # ------------------------------------------------------------------
    # STATISTICHE DI UN SINGOLO GIOCATORE
    # ------------------------------------------------------------------
    def _stats_giocatore(self, nome, ruolo=None):
        """
        Recupera le statistiche stagionali. Combinazioni valide richieste dall'API:
        id + season, oppure league + season, oppure team + season.
        Prova la stagione corrente, poi la precedente (i nuovi arrivi non hanno
        ancora dati sulla stagione appena iniziata).
        """
        chiave = normalize_str(nome)
        if chiave in self.cache["stats"]:
            return self.cache["stats"][chiave]

        if not self.api_key or self.chiamate_players >= MAX_LOOKUP:
            return None

        player_id = self.mappa_api_id.get(chiave)
        risultato = None

        for stagione in (SEASON, SEASON - 1):
            if player_id:
                params = {'id': player_id, 'season': stagione}
            else:
                # senza id serve comunque league+season: cerca fra chi gioca in Serie A
                params = {'search': nome, 'league': LEAGUE_ID_SERIE_A, 'season': stagione}
                if len(nome) < 4:
                    return None

            self.chiamate_players += 1
            risposta = self._get("players", params, timeout=8)
            if not risposta:
                continue

            statistiche = risposta[0].get('statistics', []) or []
            aggregato = None
            for st in statistiche:
                apps = st.get('games', {}).get('appearences') or 0
                if apps <= 0:
                    continue
                candidato = {
                    'presenze': apps,
                    'gol': st.get('goals', {}).get('total') or 0,
                    'assist': st.get('goals', {}).get('assists') or 0,
                    'lega': st.get('league', {}).get('name', ''),
                }
                if aggregato is None or candidato['presenze'] > aggregato['presenze']:
                    aggregato = candidato

            if aggregato:
                risultato = aggregato
                break

        self.cache["stats"][chiave] = risultato
        return risultato

    def calcola_fantamedia_proiettata(self, nome_giocatore, ruolo):
        """Proiezione della fantamedia in Serie A, pesata per lega di provenienza."""
        dati = self._stats_giocatore(nome_giocatore, ruolo)
        if not dati or dati['presenze'] <= 0:
            return None

        return self.engine.calcola_pfm_estero(
            presenze=dati['presenze'],
            gol=dati['gol'],
            assist=dati['assist'],
            lega=dati['lega'],
            fascia_squadra_destinazione='Media'
        )

    def verifica_prospetto_giovanile(self, nome_giocatore, squadra):
        """True se il giocatore ha comunque minuti ufficiali alle spalle."""
        dati = self._stats_giocatore(nome_giocatore)
        return bool(dati and dati['presenze'] > 0)


if __name__ == "__main__":
    scout = ScoutEngine()
    scout.carica_squadre_serie_a()
    rose = scout.sincronizza_rose_serie_a()
    print(f"Giocatori totali: {len(rose)}")
    scout.salva_cache()

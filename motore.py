"""
motore.py - Lo strato analitico. Solo fatti verificabili, nessuna previsione.

Regola unica: ogni numero prodotto qui deve essere ricalcolabile dal CSV.
Niente internet, niente stime di rendimento futuro, niente opinioni.
Quello che non e' noto resta dichiarato come non noto.
"""

import json
import math
import pandas as pd

SORGENTE = 'fanta-master-ai-main/Lista_Finale_Master.csv'
USCITA = 'dati_asta.json'

GIORNATE = 38
SLOT_ROSA = {'P': 3, 'D': 8, 'C': 8, 'A': 6}
SQUADRE_DEFAULT = 12
BUDGET_DEFAULT = 500


def num(serie, default=0.0):
    return pd.to_numeric(serie, errors='coerce').fillna(default)


def carica():
    df = pd.read_csv(SORGENTE, sep=';')
    df['R'] = df['R'].astype(str).str.upper().str.strip()
    for c in ['Pv', 'Mv', 'Fm', 'Gf', 'Ass', 'Rc', 'Rp', 'Amm', 'Esp',
              'Min', 'Tit', 'PvTot', 'GareSaltate', 'GareSaltateAltro',
              'FVM', 'Qt.A', 'SquadreStag', 'Gs', 'R+', 'R-']:
        df[c] = num(df.get(c))
    return df


# ---------------------------------------------------------------- CERTEZZA

# I motivi degli stop arrivano dall'API in inglese. Tradotti servono a
# spiegare, non a decorare: "ha saltato 4 partite per un problema muscolare"
# e' un'informazione, "GareSaltate: 4" non lo e'.
MOTIVI = {
    'thigh injury': 'un problema alla coscia', 'hamstring injury': 'un flessore',
    'muscle injury': 'un problema muscolare', 'muscle bruise': 'una contusione muscolare',
    'knee injury': 'un problema al ginocchio', 'jumpers knee': 'un problema al ginocchio',
    'calf injury': 'un problema al polpaccio', 'groin injury': "un problema all'inguine",
    'ankle injury': 'una caviglia', 'sprained ankle': 'una distorsione alla caviglia',
    'foot injury': 'un piede', 'toe injury': 'un dito del piede', 'heel pain': 'un tallone',
    'leg injury': 'un problema a una gamba', 'hip injury': "un problema all'anca",
    'back injury': 'la schiena', 'shoulder injury': 'una spalla',
    'hand injury': 'una mano', 'wrist injury': 'un polso', 'finger injury': 'un dito',
    'broken cheekbone': 'uno zigomo fratturato', 'broken jawbone': 'una mascella fratturata',
    'concussion': 'un trauma cranico', 'contusion': 'una contusione',
    'knock': 'una botta', 'wound': 'una ferita',
    'injury': 'un infortunio', 'injured': 'un infortunio', 'illness': 'una malattia',
    'fitness': 'una condizione fisica non a posto', 'unfit': 'una condizione fisica non a posto',
    'lacking match fitness': 'la mancanza di condizione',
    'rest': 'un turno di riposo', 'inactive': 'una scelta tecnica',
    'suspension': 'una squalifica', 'suspended': 'una squalifica',
    'red card': "un'espulsione", 'red card suspended': "un'espulsione",
    'yellow cards': 'una squalifica per cartellini',
    'personal reasons': 'motivi personali',
    'international duty': 'la nazionale', 'national team': 'la nazionale',
    'missing fixture': 'un forfait', 'coach decision': 'una scelta tecnica',
    'transfer negotiations': 'una trattativa di mercato in corso',
    'health problems': 'problemi di salute', 'broken leg': 'una gamba rotta',
    'hernia': "un'ernia", 'muscle strain': 'uno stiramento',
}


def assenza_oggi(r):
    """
    Chi e' fuori ADESSO. E' l'unica informazione del file che parla del
    presente invece che della stagione scorsa, e vale piu' di tutte le altre
    messe insieme: un fuoriclasse infortunato ad agosto e' una casella vuota
    per due mesi.

    La colonna InfortunioTipo dice sempre 'Missing Fixture' e non serve; il
    motivo vero sta in Infortunio, la data in InfortunioDal.
    """
    motivo = r.get('Infortunio')
    if not isinstance(motivo, str) or not motivo.strip():
        return None
    testo = traduci(motivo)
    data = r.get('InfortunioDal')
    data = str(data)[:10] if isinstance(data, str) else None
    return {'motivo': testo, 'dal': data,
            'grave': motivo.strip().lower() not in
                     ('yellow cards', 'suspended', 'red card', 'transfer negotiations')}


# Il ruolo che conta davvero non e' P/D/C/A: e' se quel giocatore sta dove
# arrivano i bonus. Un difensore centrale e un terzino che gioca da esterno
# alto valgono cose diverse e nel listone hanno la stessa lettera.
POSIZIONI = [
    ('Por',   'portiere', False),
    ('B;',    'braccetto in difesa a tre', False),
    ('E;W',   'esterno offensivo', True),
    ('Dd;E',  'terzino che gioca alto', True),
    ('Ds;E',  'terzino che gioca alto', True),
    ('Dd;Ds;E', 'terzino che gioca alto', True),
    ('Dd;Ds;Dc', 'difensore adattabile', False),
    ('Dd;Dc', 'terzino o centrale', False),
    ('Ds;Dc', 'terzino o centrale', False),
    ('Dc',    'difensore centrale', False),
    ('W;A',   'ala offensiva', True),
    ('W;T',   'ala o trequartista', True),
    ('T;A',   'seconda punta', True),
    ('Pc',    'punta centrale', True),
    ('W',     'ala', True),
    ('T',     'trequartista', True),
    ('C;T',   'mezzala offensiva', True),
    ('M;C',   'mediano', False),
    ('E;C',   'esterno di centrocampo', True),
    ('E',     'esterno', True),
    ('C',     'centrocampista', False),
    ('A',     'attaccante', True),
]


def posizione(r):
    esteso = str(r.get('Ruolo_Esteso') or '').strip()
    for chiave, nome, bonus in POSIZIONI:
        if esteso.startswith(chiave):
            return nome, bonus
    # Nessun ruolo deve restare senza nome: un None qui diventa NaN in pandas
    # e NaN non e' JSON valido - il file non si apre nemmeno.
    return {'P': 'portiere', 'D': 'difensore', 'C': 'centrocampista',
            'A': 'attaccante'}.get(r['R'], 'giocatore'), False


def traduci(motivo):
    if not isinstance(motivo, str) or not motivo.strip():
        return None
    return MOTIVI.get(motivo.strip().lower(), motivo.strip().lower())


def partite_possibili(r):
    """
    Quante partite AVREBBE POTUTO giocare con questa squadra.

    Non sono trentotto per tutti, ed e' l'errore che fa sembrare panchinari i
    giocatori arrivati a gennaio: tredici presenze su trentotto sono un terzo,
    tredici su diciannove sono due terzi. La colonna SquadreStag dice in quante
    maglie ha giocato quella stagione; il campionato si divide fra quelle.
    """
    maglie = max(1, int(r['SquadreStag']))
    if maglie == 1:
        return GIORNATE, False
    quota = max(int(r['Pv']), round(GIORNATE / maglie))
    return min(GIORNATE, quota), True


def certezza(r):
    """
    Quanto e' certo che sia in campo. NON quanto e' forte.

    Tre cose gia' successe e verificabili:
      - quante delle partite che poteva giocare ha giocato
      - quante delle sue presenze erano da titolare (non spezzoni)
      - quante ne ha saltate, e per cosa

    Se non esiste storico -> None. Non si inventa un numero: si dichiara che
    non si sa, ed e' un'informazione utile quanto le altre.

    Torna anche i PERCHE': un punteggio senza motivo non e' verificabile, e a
    un tetto che non sai spiegare non credi.
    """
    presenze, minuti, presenze_tot = r['Pv'], r['Min'], r['PvTot']
    titolari, saltate = r['Tit'], r['GareSaltate'] + r['GareSaltateAltro']
    if presenze <= 0 and minuti <= 0:
        return None, ['Nessun dato utile: neopromosso, arrivato da fuori, o mai impiegato.']

    possibili, cambiato = partite_possibili(r)
    perche = []

    # 1. Disponibilita': presenze sulle partite che poteva davvero giocare.
    disponibilita = min(1.0, presenze / possibili) if possibili > 0 else 0.0
    if cambiato and presenze >= possibili:
        perche.append(f'Nel 2025/26 ha cambiato squadra a stagione in corso e ha giocato '
                      f'tutte le {possibili} partite che poteva giocare.')
    elif cambiato:
        perche.append(f'Nel 2025/26 ha cambiato squadra a stagione in corso: '
                      f'{int(presenze)} presenze sulle {possibili} che poteva giocare, '
                      f'non su 38.')
    elif presenze > 0:
        perche.append(f'{int(presenze)} presenze su 38 nel campionato 2025/26.')

    # 2. Titolarita': quante presenze erano da titolare. Il minutaggio medio e'
    #    il controllo: chi parte titolare ma esce sempre al 60' non e' un titolare.
    if presenze_tot > 0 and titolari > 0:
        titolarita = min(1.0, titolari / presenze_tot)
        per_gara = minuti / presenze_tot if presenze_tot > 0 else 0
        if titolarita >= 0.8:
            perche.append(f'Titolare fisso: {int(titolari)} volte dall\'inizio '
                          f'su {int(presenze_tot)} apparizioni.')
        elif titolarita >= 0.45:
            perche.append(f'A mezzo servizio: {int(titolari)} volte titolare '
                          f'su {int(presenze_tot)}, {int(per_gara)} minuti a partita.')
        else:
            perche.append(f'Quasi sempre subentrato: solo {int(titolari)} volte titolare '
                          f'su {int(presenze_tot)}, {int(per_gara)} minuti a partita.')
    elif minuti > 0 and presenze_tot > 0:
        per_gara = minuti / presenze_tot
        titolarita = max(0.0, min(1.0, (per_gara - 15) / 65))
        perche.append(f'{int(per_gara)} minuti a partita.')
    else:
        # L'API gratuita non copre tutti: per una trentina di giocatori i
        # minuti non ci sono. Tacere e' peggio che dirlo - il punteggio esce
        # dalle sole presenze, e chi legge deve saperlo.
        titolarita = disponibilita
        perche.append('Minutaggio non disponibile: il punteggio esce dalle sole presenze.')

    # 3. Continuita': le partite saltate, col motivo quando si sa.
    giocabili = presenze_tot + saltate
    continuita = 1.0 - (saltate / giocabili) if giocabili > 0 else 1.0
    if saltate > 0:
        motivo = traduci(r.get('MotivoStop')) or traduci(r.get('MotivoAltro'))
        quante = int(saltate)
        parola = 'una partita' if quante == 1 else f'{quante} partite'
        perche.append(f'Ha saltato {parola}' + (f' per {motivo}.' if motivo else '.'))

    valore = 100 * (0.45 * disponibilita + 0.40 * titolarita + 0.15 * continuita)

    if presenze <= 0 and minuti > 0:
        valore *= 0.80
        perche.insert(0, 'Lo storico che ha e\' fuori dalla Serie A: vale, ma meno.')

    return round(valore), perche


# ---------------------------------------------------------------- RESA
# Quante partite "fittizie" di media di ruolo si aggiungono a chi ne ha giocate
# poche. Con otto, un giocatore da otto presenze pesa meta' sui suoi numeri e
# meta' sulla media: e' il freno alle meteore, e sparisce da solo per chi ha
# giocato una stagione intera.
PRUDENZA = 8


def gol_subiti(r):
    """Per un portiere e' la metrica: quanti gliene fanno a partita."""
    if r['R'] != 'P' or r['Pv'] <= 0:
        return None
    return round(r['Gs'] / r['Pv'], 2)


def cartellini(r):
    """Mezzo punto a ammonizione, un punto a espulsione. Su dodici gialli
    sono sei punti persi in una stagione: non e' rumore."""
    if r['Pv'] <= 0:
        return None
    return round((r['Amm'] * 0.5 + r['Esp'] * 1.0) / r['Pv'], 2)


def resa(r, media_ruolo):
    """
    Quanto ha reso a partita: la fantamedia, corretta per quante partite l'ha
    tenuta.

    Non si moltiplica per la disponibilita': disponibilita' e rendimento sono
    due cose diverse e vanno tenute separate, altrimenti un fuoriclasse con
    ventidue presenze finisce sotto un riempitivo che le ha giocate tutte.
    La disponibilita' e' la certezza, ed e' un numero suo.

    Su poche presenze la fantamedia non e' affidabile e viene tirata verso la
    media del ruolo. Un 7.5 in otto partite diventa un 6.9; lo stesso 7.5 in
    trentotto resta 7.5.
    """
    fm, presenze = r['Fm'], r['Pv']
    if fm <= 0 or presenze <= 0:
        return None
    corretta = (fm * presenze + media_ruolo * PRUDENZA) / (presenze + PRUDENZA)
    return round(corretta, 2)


def rigori(r):
    """
    Rc sono i rigori CALCIATI, Rp quelli PARATI: due colonne diverse che
    riguardano due mestieri diversi. Sommarle faceva risultare rigorista il
    portiere del Napoli, che di rigori ne ha parati tre e calciati zero.

    Qui non si mette un'etichetta, si mette il numero: "cinque rigori
    calciati" si spiega da solo, "rigorista" no. E un rigore solo in una
    stagione non fa il rigorista - lo si vede dalla cifra, senza doverlo
    dichiarare.
    """
    calciati = int(r['Rc']) if r['R'] != 'P' else 0
    parati = int(r['Rp']) if r['R'] == 'P' else 0
    return calciati, parati


# ---------------------------------------------------------------- MERCATO
def prezzi_di_mercato(df, squadre, budget):
    """
    Il prezzo che la stanza pagherà, non quello che vale.

    Il FVM del listone e' la scala che hanno in mano tutti: si normalizza
    sul monte crediti reale della lega, in modo che la somma dei giocatori
    che verranno effettivamente venduti pareggi i crediti in circolazione.
    """
    slot_totali = sum(SLOT_ROSA.values()) * squadre
    monte = squadre * budget
    fvm = df['FVM'].clip(lower=0)

    # Solo i primi slot_totali giocatori verranno venduti a più di un credito.
    soglia = fvm.nlargest(min(slot_totali, len(fvm))).min()
    venduti = fvm >= soglia
    crediti_a_un_credito = int(venduti.sum())
    da_distribuire = max(1, monte - crediti_a_un_credito)

    quota = fvm.where(venduti, 0)
    fattore = da_distribuire / quota.sum() if quota.sum() > 0 else 0
    prezzo = (quota * fattore + 1).round()
    return prezzo.clip(lower=1).astype(int)


def fasce(df, ruolo, squadre):
    """
    Le fasce non sono percentuali: sono la fila d'attesa.

    Con {squadre} squadre in asta, i primi {squadre} giocatori del ruolo se
    li spartiscono le squadre - uno a testa. Quelli sono la fascia 1. I
    successivi {squadre} la fascia 2, e via cosi'. La fascia dice quanti
    ne restano prima che tocchi a te: e' l'unica definizione che non
    dipende da un giudizio.
    """
    gruppo = df[df['R'] == ruolo].sort_values('prezzo_mercato', ascending=False)
    etichette, punti_rottura = [], []
    for posizione in range(len(gruppo)):
        etichette.append(min(5, posizione // squadre + 1))
    gruppo = gruppo.assign(fascia=etichette)
    for f in range(1, 6):
        blocco = gruppo[gruppo['fascia'] == f]
        if not blocco.empty:
            punti_rottura.append({
                'fascia': f,
                'da': int(blocco['prezzo_mercato'].max()),
                'a': int(blocco['prezzo_mercato'].min()),
                'quanti': int(len(blocco)),
                # Il prezzo di riferimento della fascia: quanto costa, in media,
                # una casella riempita a questo livello. E' il mattone su cui si
                # costruisce il piano.
                'rif': int(round(blocco['prezzo_mercato'].median())),
            })
    return gruppo['fascia'], punti_rottura


# ---------------------------------------------------------------- OCCASIONI
def occasioni_mod(df):
    """
    Con il modificatore di difesa attivo il metro cambia: quello che conta per
    portiere e difensori non e' la fantamedia ma la MEDIA VOTO, perche' il
    bonus lo fa la media della retroguardia. Un difensore da 6.2 di voto senza
    un gol vale piu' di uno da 5.8 che ne ha fatti tre.

    Si rifa' lo stesso confronto locale - a pari prezzo, dentro il ruolo - ma
    sulla media voto. Per centrocampisti e attaccanti non cambia nulla.
    """
    df['vantaggio_mod'] = None
    medie = {r: df[(df['R'] == r) & (df['Pv'] > 0)]['Mv'].mean() for r in ('P', 'D')}
    for ruolo in ('P', 'D'):
        blocco = df[(df['R'] == ruolo) & (df['Pv'] > 0) & (df['Mv'] > 0)].copy()
        if len(blocco) < 6:
            continue
        voto = ((blocco['Mv'] * blocco['Pv'] + medie[ruolo] * PRUDENZA)
                / (blocco['Pv'] + PRUDENZA))
        for idx, riga in blocco.iterrows():
            prezzo = max(1, riga['prezzo_mercato'])
            banda = 0.30
            while True:
                pari = blocco[(blocco['prezzo_mercato'] >= prezzo * (1 - banda)) &
                              (blocco['prezzo_mercato'] <= prezzo * (1 + banda)) &
                              (blocco.index != idx)]
                if len(pari) >= 6 or banda >= 1.0:
                    break
                banda += 0.15
            if pari.empty:
                continue
            df.at[idx, 'vantaggio_mod'] = round(voto[idx] - voto[pari.index].median(), 3)
    return df


def occasioni(df):
    """
    L'unica domanda che l'asta ti pone davvero:

        a parita' di crediti spesi, chi rende di piu' e chi gioca di piu'?

    Non "quanto vale in assoluto". Quel conto lo si puo' fare, ma finisce
    sempre per dire che i primi dieci nomi sono tutti sottopagati - il che e'
    inutile, perche' il prezzo dei fuoriclasse non lo fa il rendimento, lo fa
    il fatto che sono uno solo e li vogliono in dodici.

    Qui il confronto e' locale: ogni giocatore contro chi costa piu' o meno
    quanto lui, nel suo ruolo. Se rende sopra quel gruppo, sono crediti spesi
    meglio - e questo e' vero qualunque sia la fascia in cui stai comprando.
    """
    df['pari_prezzo'] = None      # quanti concorrenti diretti ha
    df['vantaggio'] = None        # fantamedia in piu' rispetto a loro
    df['vantaggio_cert'] = None   # certezza in piu' rispetto a loro

    for ruolo in SLOT_ROSA:
        blocco = df[(df['R'] == ruolo) & df['resa'].notna()].copy()
        if len(blocco) < 6:
            continue
        for idx, riga in blocco.iterrows():
            prezzo = max(1, riga['prezzo_mercato'])
            banda = 0.30
            while True:
                pari = blocco[(blocco['prezzo_mercato'] >= prezzo * (1 - banda)) &
                              (blocco['prezzo_mercato'] <= prezzo * (1 + banda)) &
                              (blocco.index != idx)]
                if len(pari) >= 6 or banda >= 1.0:
                    break
                banda += 0.15
            if pari.empty:
                continue
            df.at[idx, 'pari_prezzo'] = int(len(pari))
            df.at[idx, 'vantaggio'] = round(riga['resa'] - pari['resa'].median(), 2)
            certezze = pari['certezza'].dropna()
            if pd.notna(riga['certezza']) and not certezze.empty:
                df.at[idx, 'vantaggio_cert'] = int(round(riga['certezza'] - certezze.median()))
    return df


# ---------------------------------------------------------------- USCITA
def costruisci(squadre=SQUADRE_DEFAULT, budget=BUDGET_DEFAULT):
    df = carica()

    valori, note = zip(*[certezza(r) for _, r in df.iterrows()])
    df['certezza'] = valori
    df['perche'] = list(note)
    medie = {ruolo: df[(df['R'] == ruolo) & (df['Pv'] > 0)]['Fm'].mean()
             for ruolo in SLOT_ROSA}
    df['resa'] = [resa(r, medie.get(r['R'], 6.0)) for _, r in df.iterrows()]
    df['rc'], df['rp'] = zip(*[rigori(r) for _, r in df.iterrows()])
    df['gsg'] = [gol_subiti(r) for _, r in df.iterrows()]
    df['malus'] = [cartellini(r) for _, r in df.iterrows()]
    df['fuori'] = [assenza_oggi(r) for _, r in df.iterrows()]
    df['pos'], df['bonus'] = zip(*[posizione(r) for _, r in df.iterrows()])
    df['prezzo_mercato'] = prezzi_di_mercato(df, squadre, budget)

    df['fascia'] = 5
    rotture = {}
    for ruolo in SLOT_ROSA:
        etichette, punti = fasce(df, ruolo, squadre)
        df.loc[etichette.index, 'fascia'] = etichette.values
        rotture[ruolo] = punti

    df = occasioni(df)
    df = occasioni_mod(df)

    giocatori = []
    for _, r in df.iterrows():
        giocatori.append({
            'id': int(r['Id']),
            'n': str(r['Nome']),
            'r': r['R'],
            's': str(r['Squadra']),
            'p': int(r['prezzo_mercato']),
            'f': int(r['fascia']),
            'c': None if pd.isna(r['certezza']) else int(r['certezza']),
            'nc': list(r['perche']),
            'y': None if pd.isna(r['resa']) else float(r['resa']),
            'pv': int(r['Pv']),
            # Chi non ha mai giocato in Serie A ha comunque un Fm nel file:
            # e' un valore di riempimento della pipeline, fra 6.00 e 7.57, e
            # sembra un rendimento vero. Non esce di qui: senza presenze non
            # c'e' fantamedia, e la scheda dira' che non ha mai giocato.
            'mv': round(float(r['Mv']), 2) if (r['Mv'] > 0 and r['Pv'] > 0) else None,
            'fm': round(float(r['Fm']), 2) if (r['Fm'] > 0 and r['Pv'] > 0) else None,
            'g': int(r['Gf']),
            'a': int(r['Ass']),
            'rc': int(r['rc']),
            'rp': int(r['rp']),
            # Solo per i portieri: gol subiti a partita.
            'gs': None if pd.isna(r['gsg']) else float(r['gsg']),
            # Punti persi per cartellini, a partita.
            'ml': None if pd.isna(r['malus']) else float(r['malus']),
            # Chi e' fuori adesso, con motivo e data.
            'out': r['fuori'],
            # Il ruolo vero, e se e' una posizione da bonus.
            'pos': None if pd.isna(r['pos']) else str(r['pos']),
            'bn': bool(r['bonus']),
            # Rigori segnati e sbagliati: piu' preciso dei soli calciati.
            'rs': int(r['R+']), 'rx': int(r['R-']),
            # La media voto: serve alle leghe col modificatore di difesa.
            'mvp': round(float(r['Mv']), 2) if r['Mv'] > 0 else None,
            'v': None if pd.isna(r['vantaggio']) else float(r['vantaggio']),
            # Lo stesso confronto, ma sulla media voto: serve alle leghe che
            # giocano col modificatore di difesa.
            'vm': None if pd.isna(r['vantaggio_mod']) else float(r['vantaggio_mod']),
            'vc': None if pd.isna(r['vantaggio_cert']) else int(r['vantaggio_cert']),
            'q': int(r['Qt.A']),
        })

    giocatori.sort(key=lambda g: -g['p'])
    dati = {
        'aggiornato': str(df['Aggiornato'].max()) if 'Aggiornato' in df else '',
        'squadre': squadre,
        'budget': budget,
        'slot': SLOT_ROSA,
        'rotture': rotture,
        'giocatori': giocatori,
    }
    # Il file deve essere JSON valido: pandas produce NaN dove Python
    # vorrebbe None, e "NaN" non e' JSON - basta un campo per rendere l'app
    # impossibile da aprire. Si scrive solo dopo aver verificato.
    testo = json.dumps(dati, ensure_ascii=False, separators=(',', ':'),
                       allow_nan=False)
    json.loads(testo)
    with open(USCITA, 'w', encoding='utf-8') as f:
        f.write(testo)
    return dati, df


if __name__ == '__main__':
    dati, df = costruisci()
    print(f"{len(dati['giocatori'])} giocatori, aggiornato {dati['aggiornato']}")
    print('\nsenza certezza (scommesse):',
          sum(1 for g in dati['giocatori'] if g['c'] is None))
    print('\n--- fasce ---')
    for ruolo, punti in dati['rotture'].items():
        print(ruolo, [(p['fascia'], p['da'], p['a'], p['quanti']) for p in punti])
    print('\n--- top occasioni ---')
    occ = [g for g in dati['giocatori'] if g['v'] is not None and g['c'] and g['c'] >= 75]
    for ruolo in ['P','D','C','A']:
        print(f'  [{ruolo}]')
        for g in sorted([x for x in occ if x['r']==ruolo], key=lambda x: -x['v'])[:5]:
            print(f"    {g['n']:<18} {g['s']:<12} {g['p']:>3} cr  F{g['f']}  "
                  f"resa {g['y']:<5} (+{g['v']:<5}) certezza {g['c']:>3} (+{g['vc']})")

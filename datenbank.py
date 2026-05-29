"""
datenbank.py — Court Link SQLite Datenbankschicht
"""

import sqlite3
import uuid
import random
import string
from itertools import combinations
from werkzeug.security import generate_password_hash, check_password_hash
import os

DB_DATEI = os.environ.get("DB_PATH", "courtlink.db")


def verbindung():
    conn = sqlite3.connect(DB_DATEI)
    conn.row_factory = sqlite3.Row
    return conn


def initialisiere_db():
    conn = verbindung()
    c = conn.cursor()

    # teams: hat jetzt ein team_passwort_hash Feld
    c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            team_passwort_hash TEXT NOT NULL,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS spieler (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            alias TEXT NOT NULL,
            team_id TEXT NOT NULL,
            passwort_hash TEXT,
            ist_gast INTEGER DEFAULT 0,
            claim_code TEXT UNIQUE,
            punkte REAL DEFAULT 0,
            spiele INTEGER DEFAULT 0,
            siege INTEGER DEFAULT 0,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS spieltage (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            modus TEXT NOT NULL,
            aktuelle_runde INTEGER DEFAULT 1,
            gesamt_runden INTEGER DEFAULT 1,
            status TEXT DEFAULT 'aktiv',
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    # matches: hat jetzt ein runde Feld
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            spieltag_id TEXT NOT NULL,
            runde INTEGER NOT NULL DEFAULT 1,
            team1_s1_id TEXT NOT NULL,
            team1_s2_id TEXT NOT NULL,
            team2_s1_id TEXT NOT NULL,
            team2_s2_id TEXT NOT NULL,
            tore_team1 INTEGER DEFAULT NULL,
            tore_team2 INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'offen',
            FOREIGN KEY (spieltag_id) REFERENCES spieltage(id)
        )
    """)

    conn.commit()
    conn.close()


def _code(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))


# ══ Team ═══════════════════════════════════════════════════════════

def team_erstellen(name, team_passwort):
    conn = verbindung()
    tid  = str(uuid.uuid4())[:8]
    code = _code(6)
    pw_hash = generate_password_hash(team_passwort)
    conn.execute(
        "INSERT INTO teams (id, name, code, team_passwort_hash) VALUES (?, ?, ?, ?)",
        (tid, name, code, pw_hash)
    )
    conn.commit()
    team = dict(conn.execute("SELECT id,name,code FROM teams WHERE id=?", (tid,)).fetchone())
    conn.close()
    return team


def team_per_code(code):
    conn = verbindung()
    row  = conn.execute("SELECT * FROM teams WHERE code=?", (code.upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def team_passwort_pruefen(team, passwort):
    return check_password_hash(team['team_passwort_hash'], passwort)


def team_per_id(tid):
    conn = verbindung()
    row  = conn.execute("SELECT id,name,code FROM teams WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ══ Spieler ════════════════════════════════════════════════════════

def spieler_registrieren(name, alias, passwort, team_id):
    conn = verbindung()
    if conn.execute(
        "SELECT id FROM spieler WHERE LOWER(name)=LOWER(?) AND team_id=?",
        (name, team_id)
    ).fetchone():
        conn.close()
        return None, "Dieser Name ist im Team bereits vergeben"

    sid     = str(uuid.uuid4())[:8]
    alias   = alias.strip() or name
    pw_hash = generate_password_hash(passwort)
    conn.execute(
        "INSERT INTO spieler (id,name,alias,team_id,passwort_hash,ist_gast) VALUES (?,?,?,?,?,0)",
        (sid, name, alias, team_id, pw_hash)
    )
    conn.commit()
    sp = _sp_ohne_hash(conn, sid)
    conn.close()
    return sp, None


def spieler_einloggen(name, passwort, team_id):
    conn = verbindung()
    row  = conn.execute(
        "SELECT * FROM spieler WHERE LOWER(name)=LOWER(?) AND team_id=? AND ist_gast=0",
        (name, team_id)
    ).fetchone()
    conn.close()
    if not row:
        return None, "Name oder Passwort falsch"
    sp = dict(row)
    if not check_password_hash(sp['passwort_hash'], passwort):
        return None, "Name oder Passwort falsch"
    sp.pop('passwort_hash', None)
    return sp, None


def spieler_als_gast(name, alias, team_id):
    conn = verbindung()
    if conn.execute(
        "SELECT id FROM spieler WHERE LOWER(name)=LOWER(?) AND team_id=?",
        (name, team_id)
    ).fetchone():
        conn.close()
        return None, "Dieser Name ist im Team bereits vergeben"

    sid        = str(uuid.uuid4())[:8]
    alias      = alias.strip() or name
    claim_code = _code(8)
    conn.execute(
        "INSERT INTO spieler (id,name,alias,team_id,ist_gast,claim_code) VALUES (?,?,?,?,1,?)",
        (sid, name, alias, team_id, claim_code)
    )
    conn.commit()
    sp = _sp_ohne_hash(conn, sid)
    conn.close()
    return sp, None


def gast_uebernehmen(claim_code, neuer_name, neuer_alias, passwort):
    conn = verbindung()
    row  = conn.execute(
        "SELECT * FROM spieler WHERE claim_code=? AND ist_gast=1",
        (claim_code.upper(),)
    ).fetchone()
    if not row:
        conn.close()
        return None, "Ungültiger oder bereits verwendeter Code"

    sp    = dict(row)
    alias = neuer_alias.strip() or neuer_name
    conn.execute(
        "UPDATE spieler SET name=?,alias=?,passwort_hash=?,ist_gast=0,claim_code=NULL WHERE id=?",
        (neuer_name, alias, generate_password_hash(passwort), sp['id'])
    )
    conn.commit()
    result = _sp_ohne_hash(conn, sp['id'])
    conn.close()
    return result, None


def _sp_ohne_hash(conn, sid):
    row = conn.execute(
        "SELECT id,name,alias,team_id,ist_gast,claim_code,punkte,spiele,siege FROM spieler WHERE id=?",
        (sid,)
    ).fetchone()
    return dict(row) if row else {}


def spieler_des_teams(team_id):
    conn = verbindung()
    rows = conn.execute(
        "SELECT id,name,alias,team_id,ist_gast,punkte,spiele,siege FROM spieler WHERE team_id=? ORDER BY punkte DESC",
        (team_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def spieler_loeschen(sid, team_id):
    conn = verbindung()
    conn.execute("DELETE FROM spieler WHERE id=? AND team_id=?", (sid, team_id))
    conn.commit()
    conn.close()


def spieler_claim_code(sid, team_id):
    conn = verbindung()
    row  = conn.execute(
        "SELECT claim_code,alias FROM spieler WHERE id=? AND team_id=? AND ist_gast=1",
        (sid, team_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ══ Team-Generierung ═══════════════════════════════════════════════

def _mische_teams(spieler_liste, modus):
    """Gibt 2er-Teams zurück als Liste von [sp1, sp2]."""
    n = len(spieler_liste) // 2
    if modus == 'ranked':
        sortiert = sorted(spieler_liste, key=lambda s: s['punkte'], reverse=True)
        obere    = sortiert[:n];  random.shuffle(obere)
        untere   = sortiert[n:];  random.shuffle(untere)
        return [[obere[i], untere[i]] for i in range(n)]            # gutes ranked systhem, soweit ich das beurteilen kann
    else:
        gem = spieler_liste.copy(); random.shuffle(gem)
        return [[gem[i], gem[i+1]] for i in range(0, len(gem), 2)]


def _round_robin_schedule(teams):
    """
    Erstellt einen Round-Robin-Spielplan.
    Jedes Team-Paar spielt genau einmal gegeneinander.
    Gibt Liste von Runden zurück: [ [(t1,t2),(t3,t4),...], [(t1,t3),...], ... ]
    
    Verwendet den Standard-Kreis-Algorithmus damit pro Runde
    jedes Team maximal einmal spielt.
    """
    n = len(teams)
    # Bei ungerader Anzahl: Freilos-Team hinzufügen (wird herausgefiltert)
    lst = teams[:]
    if n % 2 == 1:
        lst.append(None)

    runden = []
    anz    = len(lst)
    for r in range(anz - 1):
        runde = []
        for i in range(anz // 2):
            t1 = lst[i]
            t2 = lst[anz - 1 - i]
            if t1 is not None and t2 is not None:
                runde.append((t1, t2))
        runden.append(runde)
        # Rotation: alle außer erstem Element rotieren
        lst = [lst[0]] + [lst[-1]] + lst[1:-1]

    return runden


# ══ Spieltag ═══════════════════════════════════════════════════════

def spieltag_erstellen(team_id, modus, spieler_ids):
    """
    Erstellt einen Spieltag mit vollständigem Round-Robin-Plan.
    Alle Runden werden sofort in der DB gespeichert,
    aber nur Runde 1 ist am Anfang aktiv sichtbar.
    """
    conn = verbindung()
    placeholders = ','.join('?' * len(spieler_ids))
    rows = conn.execute(
        f"SELECT id,name,alias,ist_gast,punkte,spiele,siege FROM spieler WHERE id IN ({placeholders}) AND team_id=?",
        (*spieler_ids, team_id)
    ).fetchall()
    spieler_liste = [dict(r) for r in rows]

    if len(spieler_liste) < 4:
        conn.close()
        return None, "Mindestens 4 Spieler für ein Turnier nötig"
    if len(spieler_liste) % 2 != 0:
        conn.close()
        return None, "Gerade Anzahl an Spielern nötig"

    # 2er-Teams bilden
    padel_teams = _mische_teams(spieler_liste, modus)

    # Round-Robin-Plan erstellen
    runden_plan = _round_robin_schedule(padel_teams)
    gesamt_runden = len(runden_plan)

    st_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO spieltage (id,team_id,modus,aktuelle_runde,gesamt_runden) VALUES (?,?,?,1,?)",
        (st_id, team_id, modus, gesamt_runden)
    )

    # Alle Matches aller Runden speichern
    for runden_nr, runde in enumerate(runden_plan, start=1):
        for (t1, t2) in runde:
            mid = str(uuid.uuid4())[:8]
            conn.execute("""
                INSERT INTO matches
                (id,spieltag_id,runde,team1_s1_id,team1_s2_id,team2_s1_id,team2_s2_id)
                VALUES (?,?,?,?,?,?,?)
            """, (mid, st_id, runden_nr, t1[0]['id'], t1[1]['id'], t2[0]['id'], t2[1]['id']))

    conn.commit()
    conn.close()

    return _spieltag_details(st_id), None


def _spieltag_details(st_id):
    """Gibt Spieltag mit Matches der aktuellen Runde zurück."""
    conn = verbindung()
    st   = dict(conn.execute("SELECT * FROM spieltage WHERE id=?", (st_id,)).fetchone())
    conn.close()

    st['matches']         = spieltag_matches(st_id, st['aktuelle_runde'])
    st['alle_ergebnisse'] = spieltag_alle_ergebnisse(st_id)
    return st


def spieltag_matches(spieltag_id, runde=None):
    """Gibt Matches einer bestimmten Runde zurück (oder alle wenn runde=None)."""
    conn = verbindung()
    if runde is not None:
        rows = conn.execute(
            "SELECT * FROM matches WHERE spieltag_id=? AND runde=? ORDER BY rowid",
            (spieltag_id, runde)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM matches WHERE spieltag_id=? ORDER BY runde,rowid",
            (spieltag_id,)
        ).fetchall()

    ergebnis = []
    for m in rows:
        m = dict(m)
        def sp(sid):
            r = conn.execute(
                "SELECT id,name,alias,ist_gast,punkte FROM spieler WHERE id=?", (sid,)
            ).fetchone()
            return dict(r) if r else {}
        ergebnis.append({
            'id': m['id'], 'runde': m['runde'], 'status': m['status'],
            'tore_team1': m['tore_team1'], 'tore_team2': m['tore_team2'],
            'team1': [sp(m['team1_s1_id']), sp(m['team1_s2_id'])],
            'team2': [sp(m['team2_s1_id']), sp(m['team2_s2_id'])],
        })
    conn.close()
    return ergebnis


def spieltag_alle_ergebnisse(spieltag_id):
    """Gibt alle gespielten Matches aller Runden zurück (für Übersicht)."""
    conn = verbindung()
    rows = conn.execute(
        "SELECT * FROM matches WHERE spieltag_id=? AND status='gespielt' ORDER BY runde,rowid",
        (spieltag_id,)
    ).fetchall()
    conn.close()
    # Vereinfachte Darstellung für die Übersicht
    result = []
    for m in rows:
        m = dict(m)
        conn2 = verbindung()
        def sp_name(sid):
            r = conn2.execute("SELECT alias FROM spieler WHERE id=?", (sid,)).fetchone()
            return r[0] if r else '?'
        result.append({
            'runde': m['runde'],
            't1': f"{sp_name(m['team1_s1_id'])} & {sp_name(m['team1_s2_id'])}",
            't2': f"{sp_name(m['team2_s1_id'])} & {sp_name(m['team2_s2_id'])}",
            'score': f"{m['tore_team1']}:{m['tore_team2']}"
        })
        conn2.close()
    return result


def ergebnis_eintragen(match_id, tore1, tore2):
    """Trägt Ergebnis ein, verteilt Punkte und prüft ob Runde fertig ist."""
    conn = verbindung()
    m    = dict(conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone())

    if tore1 > tore2:   p1,p2,s1,s2 = 3,0,1,0
    elif tore2 > tore1: p1,p2,s1,s2 = 0,3,0,1
    else:               p1,p2,s1,s2 = 1,1,0,0

    for sid in [m['team1_s1_id'], m['team1_s2_id']]:
        conn.execute("UPDATE spieler SET punkte=punkte+?,spiele=spiele+1,siege=siege+? WHERE id=?", (p1,s1,sid))
    for sid in [m['team2_s1_id'], m['team2_s2_id']]:
        conn.execute("UPDATE spieler SET punkte=punkte+?,spiele=spiele+1,siege=siege+? WHERE id=?", (p2,s2,sid))

    conn.execute(
        "UPDATE matches SET tore_team1=?,tore_team2=?,status='gespielt' WHERE id=?",
        (tore1, tore2, match_id)
    )
    conn.commit()

    # Prüfen ob alle Matches dieser Runde fertig sind
    st = dict(conn.execute("SELECT * FROM spieltage WHERE id=?", (m['spieltag_id'],)).fetchone())
    offen = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE spieltag_id=? AND runde=? AND status='offen'",
        (m['spieltag_id'], st['aktuelle_runde'])
    ).fetchone()[0]

    naechste_runde_bereit = False
    if offen == 0 and st['aktuelle_runde'] < st['gesamt_runden']:
        # Nächste Runde freischalten
        conn.execute(
            "UPDATE spieltage SET aktuelle_runde=aktuelle_runde+1 WHERE id=?",
            (m['spieltag_id'],)
        )
        conn.commit()
        naechste_runde_bereit = True

    conn.close()
    return naechste_runde_bereit


def spieltag_beenden(spieltag_id):
    conn = verbindung()
    conn.execute("UPDATE spieltage SET status='beendet' WHERE id=?", (spieltag_id,))
    conn.commit()
    conn.close()


def aktiver_spieltag(team_id):
    conn = verbindung()
    row  = conn.execute(
        "SELECT * FROM spieltage WHERE team_id=? AND status='aktiv' ORDER BY erstellt_am DESC LIMIT 1",
        (team_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    st = dict(row)
    st['matches']         = spieltag_matches(st['id'], st['aktuelle_runde'])
    st['alle_ergebnisse'] = spieltag_alle_ergebnisse(st['id'])
    return st


def ranking(team_id):
    return spieler_des_teams(team_id)

def spieltag_team_ranking(spieltag_id):
    """
    Berechnet das Ranking der 2er-Teams für einen Spieltag.
    Wertet alle gespielten Matches aus und summiert die Punkte pro Team.
    """
    conn = verbindung()

    matches = conn.execute(
        "SELECT * FROM matches WHERE spieltag_id=? AND status='gespielt'",
        (spieltag_id,)
    ).fetchall()

    # Dict: team_key → { spieler, punkte, siege, spiele }
    teams = {}

    for m in matches:
        m = dict(m)

        if m['tore_team1'] > m['tore_team2']:
            p1, p2, s1, s2 = 3, 0, 1, 0
        elif m['tore_team2'] > m['tore_team1']:
            p1, p2, s1, s2 = 0, 3, 0, 1
        else:
            p1, p2, s1, s2 = 1, 1, 0, 0

        # Hilfsfunktion: Spieler-Namen laden
        def sp_info(sid):
            r = conn.execute(
                "SELECT alias, ist_gast FROM spieler WHERE id=?", (sid,)
            ).fetchone()
            return dict(r) if r else {'alias': '?', 'ist_gast': 0}

        # Team 1 als sortierten Key speichern (damit Reihenfolge egal)
        key1 = tuple(sorted([m['team1_s1_id'], m['team1_s2_id']]))
        key2 = tuple(sorted([m['team2_s1_id'], m['team2_s2_id']]))

        if key1 not in teams:
            teams[key1] = {
                'spieler': [sp_info(m['team1_s1_id']), sp_info(m['team1_s2_id'])],
                'punkte': 0, 'siege': 0, 'spiele': 0
            }
        if key2 not in teams:
            teams[key2] = {
                'spieler': [sp_info(m['team2_s1_id']), sp_info(m['team2_s2_id'])],
                'punkte': 0, 'siege': 0, 'spiele': 0
            }

        teams[key1]['punkte'] += p1
        teams[key1]['siege']  += s1
        teams[key1]['spiele'] += 1

        teams[key2]['punkte'] += p2
        teams[key2]['siege']  += s2
        teams[key2]['spiele'] += 1

    conn.close()

    # Sortiert nach Punkten, dann Siegen
    sortiert = sorted(teams.values(), key=lambda t: (t['punkte'], t['siege']), reverse=True)
    return sortiert

def spieltag_team_ranking(spieltag_id):
    conn = verbindung()
    matches = conn.execute(
        "SELECT * FROM matches WHERE spieltag_id=? AND status='gespielt'",
        (spieltag_id,)
    ).fetchall()

    teams = {}
    for m in matches:
        m = dict(m)
        if m['tore_team1'] > m['tore_team2']:   p1,p2,s1,s2 = 3,0,1,0
        elif m['tore_team2'] > m['tore_team1']: p1,p2,s1,s2 = 0,3,0,1
        else:                                    p1,p2,s1,s2 = 1,1,0,0

        def sp_info(sid):
            r = conn.execute("SELECT alias, ist_gast FROM spieler WHERE id=?", (sid,)).fetchone()
            return dict(r) if r else {'alias': '?', 'ist_gast': 0}

        key1 = tuple(sorted([m['team1_s1_id'], m['team1_s2_id']]))
        key2 = tuple(sorted([m['team2_s1_id'], m['team2_s2_id']]))

        if key1 not in teams:
            teams[key1] = {'spieler': [sp_info(m['team1_s1_id']), sp_info(m['team1_s2_id'])], 'punkte':0,'siege':0,'spiele':0}
        if key2 not in teams:
            teams[key2] = {'spieler': [sp_info(m['team2_s1_id']), sp_info(m['team2_s2_id'])], 'punkte':0,'siege':0,'spiele':0}

        teams[key1]['punkte'] += p1; teams[key1]['siege'] += s1; teams[key1]['spiele'] += 1
        teams[key2]['punkte'] += p2; teams[key2]['siege'] += s2; teams[key2]['spiele'] += 1

    conn.close()
    return sorted(teams.values(), key=lambda t: (t['punkte'], t['siege']), reverse=True)
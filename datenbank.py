"""
datenbank.py — Court Link SQLite Datenbankschicht
"""

import sqlite3
import uuid
import random
import string
import json
from datetime import datetime
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS spieltag_archiv (
            id TEXT PRIMARY KEY,
            spieltag_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            modus TEXT NOT NULL,
            gesamt_runden INTEGER NOT NULL,
            ranking_json TEXT NOT NULL,
            teams_json TEXT NOT NULL,
            beendet_am TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            alias TEXT NOT NULL DEFAULT '',
            passwort_hash TEXT NOT NULL,
            erstellt_am TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # migration: add alias column to existing databases
    try:
        c.execute("ALTER TABLE accounts ADD COLUMN alias TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS account_team (
            account_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            spieler_id TEXT NOT NULL,
            ist_admin INTEGER DEFAULT 0,
            PRIMARY KEY (account_id, team_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (spieler_id) REFERENCES spieler(id)
        )
    """)

    # Migrationen: neue Spalten zu bestehenden Tabellen
    for col_def in [
        "admin_account_id TEXT",
        "ist_plus INTEGER DEFAULT 0",
        "plus_bis TEXT DEFAULT NULL",
        "americano_modus INTEGER DEFAULT 1",
    ]:
        try:
            c.execute(f"ALTER TABLE teams ADD COLUMN {col_def}")
        except Exception:
            pass

    for col_def in [
        "hat_vereinsabo INTEGER DEFAULT 0",
        "vereinsabo_bis TEXT DEFAULT NULL",
        "stripe_id TEXT DEFAULT NULL",
    ]:
        try:
            c.execute(f"ALTER TABLE accounts ADD COLUMN {col_def}")
        except Exception:
            pass

    try:
        c.execute("ALTER TABLE account_team ADD COLUMN ist_admin INTEGER DEFAULT 0")
    except Exception:
        pass

    conn.commit()

    # Datenmigration: admin_account_id für bestehende Teams setzen
    c.execute("""
        UPDATE teams SET admin_account_id = (
            SELECT account_id FROM account_team
            WHERE team_id = teams.id
            ORDER BY rowid ASC LIMIT 1
        )
        WHERE admin_account_id IS NULL
    """)

    # ist_admin = 1 für bestehende Admins setzen
    c.execute("""
        UPDATE account_team SET ist_admin = 1
        WHERE EXISTS (
            SELECT 1 FROM teams
            WHERE teams.id = account_team.team_id
            AND teams.admin_account_id = account_team.account_id
        ) AND ist_admin = 0
    """)

    conn.commit()
    conn.close()


def _code(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))


# ══ Team ═══════════════════════════════════════════════════════════

def team_erstellen(name, team_passwort, account_id=None):
    conn = verbindung()
    tid  = str(uuid.uuid4())[:8]
    code = _code(6)
    pw_hash = generate_password_hash(team_passwort)
    conn.execute(
        "INSERT INTO teams (id, name, code, team_passwort_hash, admin_account_id) VALUES (?, ?, ?, ?, ?)",
        (tid, name, code, pw_hash, account_id)
    )
    conn.commit()
    team = dict(conn.execute("SELECT id,name,code,admin_account_id FROM teams WHERE id=?", (tid,)).fetchone())
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
    row  = conn.execute("SELECT id,name,code,admin_account_id,americano_modus FROM teams WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def americano_status_laden(team_id):
    conn = verbindung()
    row = conn.execute("SELECT americano_modus FROM teams WHERE id=?", (team_id,)).fetchone()
    conn.close()
    return row['americano_modus'] if row else 1


def americano_status_setzen(team_id, wert):
    conn = verbindung()
    conn.execute("UPDATE teams SET americano_modus=? WHERE id=?", (int(wert), team_id))
    conn.commit()
    conn.close()


# ══ Accounts ═══════════════════════════════════════════════════════

def account_registrieren(name, passwort, alias=""):
    conn = verbindung()
    if conn.execute("SELECT id FROM accounts WHERE LOWER(name)=LOWER(?)", (name,)).fetchone():
        conn.close()
        return None, "Dieser Name ist bereits vergeben"
    aid     = str(uuid.uuid4())[:8]
    pw_hash = generate_password_hash(passwort)
    eff_alias = alias.strip() or name
    conn.execute("INSERT INTO accounts (id, name, alias, passwort_hash) VALUES (?,?,?,?)", (aid, name, eff_alias, pw_hash))
    conn.commit()
    row = conn.execute("SELECT id, name, alias, erstellt_am FROM accounts WHERE id=?", (aid,)).fetchone()
    conn.close()
    return dict(row), None


def account_einloggen(name, passwort):
    conn = verbindung()
    row  = conn.execute("SELECT * FROM accounts WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    conn.close()
    if not row:
        return None, "Name oder Passwort falsch"
    acc = dict(row)
    if not check_password_hash(acc['passwort_hash'], passwort):
        return None, "Name oder Passwort falsch"
    acc.pop('passwort_hash', None)
    if not acc.get('alias'):
        acc['alias'] = acc['name']
    return acc, None


def account_per_id(account_id):
    conn = verbindung()
    row  = conn.execute("SELECT id, name, alias, erstellt_am FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def account_teams(account_id):
    conn = verbindung()
    rows = conn.execute(
        """SELECT t.id, t.name, t.code, t.admin_account_id, at.spieler_id, at.ist_admin
           FROM account_team at
           JOIN teams t ON t.id = at.team_id
           WHERE at.account_id=?""",
        (account_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def account_stats_aktualisieren(account_id):
    """Gibt aggregierte Stats über alle Teams des Accounts zurück."""
    conn = verbindung()
    row  = conn.execute(
        """SELECT COALESCE(SUM(s.punkte),0) AS punkte,
                  COALESCE(SUM(s.spiele),0) AS spiele,
                  COALESCE(SUM(s.siege),0)  AS siege
           FROM account_team at
           JOIN spieler s ON s.id = at.spieler_id
           WHERE at.account_id=?""",
        (account_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {'punkte': 0, 'spiele': 0, 'siege': 0}


def account_team_verknuepfen(account_id, team_id, spieler_id, ist_admin=0):
    conn = verbindung()
    conn.execute(
        "INSERT OR REPLACE INTO account_team (account_id, team_id, spieler_id, ist_admin) VALUES (?,?,?,?)",
        (account_id, team_id, spieler_id, ist_admin)
    )
    conn.commit()
    conn.close()


def account_alias_aendern(account_id, neuer_alias):
    conn = verbindung()
    conn.execute(
        "UPDATE accounts SET alias=? WHERE id=?",
        (neuer_alias, account_id)
    )
    conn.execute(
        """UPDATE spieler SET alias=?
           WHERE id IN (SELECT spieler_id FROM account_team WHERE account_id=?)""",
        (neuer_alias, account_id)
    )
    conn.commit()
    acc = account_per_id(account_id)
    conn.close()
    return acc


def team_beitreten(account_id, code, team_passwort, spieler_name, alias):
    """Account tritt einem bestehenden Team bei und erhält einen Spieler-Eintrag."""
    team = team_per_code(code)
    if not team:
        return None, None, "Team nicht gefunden"
    if not team_passwort_pruefen(team, team_passwort):
        return None, None, "Team-Passwort falsch"

    conn = verbindung()
    existing = conn.execute(
        "SELECT spieler_id FROM account_team WHERE account_id=? AND team_id=?",
        (account_id, team['id'])
    ).fetchone()
    conn.close()
    if existing:
        return None, None, "Du bist bereits Mitglied dieses Teams"

    acc = account_per_id(account_id)
    name = spieler_name.strip() or acc['name']
    spieler, fehler = spieler_registrieren(name, alias, str(uuid.uuid4()), team['id'])
    if fehler:
        return None, None, fehler

    account_team_verknuepfen(account_id, team['id'], spieler['id'])
    return team, spieler, None


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


def gast_uebernehmen(claim_code, account_id):
    """Übernimmt einen Gast-Spieler und verknüpft ihn mit dem Account."""
    conn = verbindung()
    row  = conn.execute(
        "SELECT * FROM spieler WHERE claim_code=? AND ist_gast=1",
        (claim_code.upper(),)
    ).fetchone()
    if not row:
        conn.close()
        return None, None, "Ungültiger oder bereits verwendeter Code"

    sp = dict(row)
    conn.execute(
        "UPDATE spieler SET ist_gast=0, claim_code=NULL WHERE id=?",
        (sp['id'],)
    )
    conn.commit()
    result = _sp_ohne_hash(conn, sp['id'])
    conn.close()

    account_team_verknuepfen(account_id, sp['team_id'], sp['id'])
    return team_per_id(sp['team_id']), result, None


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
    Erstellt einen Spieltag.
    Round-Robin: alle Runden sofort gespeichert.
    Americano:   nur Runde 1 gespeichert; Folgerunden werden dynamisch nach Ergebnissen generiert.
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
    team_row = conn.execute("SELECT americano_modus FROM teams WHERE id=?", (team_id,)).fetchone()
    americano_an = (team_row['americano_modus'] == 1) if team_row else True

    if americano_an and len(spieler_liste) % 4 != 0:
        conn.close()
        return None, "Americano-Modus ist aktiv — bitte genau 4, 8 oder 12 Spieler wählen"

    padel_teams = _mische_teams(spieler_liste, modus)

    runden_plan = _round_robin_schedule(padel_teams)
    gesamt_runden = len(runden_plan)

    st_id = str(uuid.uuid4())[:8]
    conn.execute(
        "INSERT INTO spieltage (id,team_id,modus,aktuelle_runde,gesamt_runden) VALUES (?,?,?,1,?)",
        (st_id, team_id, modus, gesamt_runden)
    )

    # Americano AN: nur Runde 1 speichern; Americano AUS: alle Runden sofort
    runden_zum_speichern = [runden_plan[0]] if americano_an else runden_plan
    for runden_nr, runde in enumerate(runden_zum_speichern, start=1):
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
    naechste_runde_nr = None
    if offen == 0 and st['aktuelle_runde'] < st['gesamt_runden']:
        team_row = conn.execute("SELECT americano_modus FROM teams WHERE id=?", (st['team_id'],)).fetchone()
        conn.close()
        if team_row and team_row['americano_modus'] == 1:
            spieltag_runde_generieren(m['spieltag_id'])
        conn2 = verbindung()
        conn2.execute("UPDATE spieltage SET aktuelle_runde=aktuelle_runde+1 WHERE id=?", (m['spieltag_id'],))
        conn2.commit()
        conn2.close()
        naechste_runde_bereit = True
        naechste_runde_nr = st['aktuelle_runde'] + 1
    else:
        conn.close()
    return naechste_runde_bereit, naechste_runde_nr


def ergebnisse_eintragen_bulk(ergebnisse):
    """Trägt eine Liste von Ergebnissen atomar in einer einzigen Transaktion ein."""
    conn = verbindung()
    spieltag_id = None

    for e in ergebnisse:
        row = conn.execute("SELECT * FROM matches WHERE id=?", (e['match_id'],)).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Match {e['match_id']} nicht gefunden")
        m = dict(row)
        if m['status'] == 'gespielt':
            continue

        t1, t2 = int(e['tore_team1']), int(e['tore_team2'])
        if t1 > t2:   p1, p2, s1, s2 = 3, 0, 1, 0
        elif t2 > t1: p1, p2, s1, s2 = 0, 3, 0, 1
        else:          p1, p2, s1, s2 = 1, 1, 0, 0

        for sid in [m['team1_s1_id'], m['team1_s2_id']]:
            conn.execute("UPDATE spieler SET punkte=punkte+?,spiele=spiele+1,siege=siege+? WHERE id=?", (p1, s1, sid))
        for sid in [m['team2_s1_id'], m['team2_s2_id']]:
            conn.execute("UPDATE spieler SET punkte=punkte+?,spiele=spiele+1,siege=siege+? WHERE id=?", (p2, s2, sid))

        conn.execute(
            "UPDATE matches SET tore_team1=?,tore_team2=?,status='gespielt' WHERE id=?",
            (t1, t2, e['match_id'])
        )
        spieltag_id = m['spieltag_id']

    conn.commit()
    conn.close()

    naechste_runde = False
    naechste_runde_nr = None
    if spieltag_id:
        conn2 = verbindung()
        st    = dict(conn2.execute("SELECT * FROM spieltage WHERE id=?", (spieltag_id,)).fetchone())
        offen = conn2.execute(
            "SELECT COUNT(*) FROM matches WHERE spieltag_id=? AND runde=? AND status='offen'",
            (spieltag_id, st['aktuelle_runde'])
        ).fetchone()[0]
        team_row = conn2.execute("SELECT americano_modus FROM teams WHERE id=?", (st['team_id'],)).fetchone()
        americano_an = (team_row['americano_modus'] == 1) if team_row else True
        conn2.close()
        if offen == 0 and st['aktuelle_runde'] < st['gesamt_runden']:
            if americano_an:
                spieltag_runde_generieren(spieltag_id)
            conn3 = verbindung()
            conn3.execute("UPDATE spieltage SET aktuelle_runde=aktuelle_runde+1 WHERE id=?", (spieltag_id,))
            conn3.commit()
            conn3.close()
            naechste_runde = True
            naechste_runde_nr = st['aktuelle_runde'] + 1

    return naechste_runde, naechste_runde_nr


def spieltag_archivieren(spieltag_id):
    """Speichert Abschluss-Snapshot eines Spieltages (wird von spieltag_beenden aufgerufen)."""
    conn = verbindung()
    st = conn.execute("SELECT * FROM spieltage WHERE id=?", (spieltag_id,)).fetchone()
    if not st:
        conn.close()
        return
    st = dict(st)

    # Alle beteiligten Spieler ermitteln
    rows = conn.execute(
        """SELECT DISTINCT sid FROM (
            SELECT team1_s1_id AS sid FROM matches WHERE spieltag_id=?
            UNION SELECT team1_s2_id FROM matches WHERE spieltag_id=?
            UNION SELECT team2_s1_id FROM matches WHERE spieltag_id=?
            UNION SELECT team2_s2_id FROM matches WHERE spieltag_id=?
        )""",
        (spieltag_id, spieltag_id, spieltag_id, spieltag_id)
    ).fetchall()

    spieler_ranking = []
    for r in rows:
        sp = conn.execute(
            "SELECT id,name,alias,punkte,spiele,siege FROM spieler WHERE id=?", (r[0],)
        ).fetchone()
        if sp:
            spieler_ranking.append(dict(sp))
    spieler_ranking.sort(key=lambda s: (s['punkte'], s['siege']), reverse=True)
    conn.close()

    team_ranking = spieltag_team_ranking(spieltag_id)

    conn2 = verbindung()
    archiv_id  = str(uuid.uuid4())[:8]
    beendet_am = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn2.execute(
        """INSERT INTO spieltag_archiv
           (id, spieltag_id, team_id, modus, gesamt_runden, ranking_json, teams_json, beendet_am)
           VALUES (?,?,?,?,?,?,?,?)""",
        (archiv_id, spieltag_id, st['team_id'], st['modus'], st['gesamt_runden'],
         json.dumps(spieler_ranking), json.dumps(team_ranking), beendet_am)
    )
    conn2.commit()
    conn2.close()


def spieltag_beenden(spieltag_id):
    spieltag_archivieren(spieltag_id)
    conn = verbindung()
    conn.execute("UPDATE spieltage SET status='beendet' WHERE id=?", (spieltag_id,))
    conn.commit()
    conn.close()


def spieltag_archiv_alle(team_id):
    """Gibt alle archivierten Spieltage eines Teams zurück."""
    conn  = verbindung()
    rows  = conn.execute(
        "SELECT * FROM spieltag_archiv WHERE team_id=? ORDER BY beendet_am DESC",
        (team_id,)
    ).fetchall()
    conn.close()
    ergebnis = []
    for r in rows:
        r = dict(r)
        r['ranking'] = json.loads(r['ranking_json'])
        r['teams']   = json.loads(r['teams_json'])
        del r['ranking_json']
        del r['teams_json']
        ergebnis.append(r)
    return ergebnis


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


# ══ Americano ══════════════════════════════════════════════════════

def _americano_paarungen(teams_sortiert, gespielt_set, gewinner_vs_verlierer=False):
    """
    Greedy-Paarung: Bestes Team bekommt schlechtesten verfügbaren Gegner (gewinner_vs_verlierer=True)
    oder besten verfügbaren Gegner (False).
    Vermeidet Rematches soweit möglich; akzeptiert sie falls keine Alternative existiert.
    teams_sortiert: Liste von (s1_id, s2_id)-Tuples, nach Spieltag-Punkten absteigend.
    gespielt_set:   set von frozenset({frozenset(team1_ids), frozenset(team2_ids)})
    """
    unmatched = list(teams_sortiert)
    result = []
    while len(unmatched) >= 2:
        t1 = unmatched.pop(0)
        t1_frozen = frozenset(t1)
        if gewinner_vs_verlierer:
            # Schlechtesten verfügbaren Nicht-Rematch-Partner suchen
            idx = len(unmatched) - 1
            while idx > 0:
                if frozenset([t1_frozen, frozenset(unmatched[idx])]) not in gespielt_set:
                    break
                idx -= 1
        else:
            # Besten verfügbaren Nicht-Rematch-Partner suchen
            idx = 0
            while idx < len(unmatched):
                if frozenset([t1_frozen, frozenset(unmatched[idx])]) not in gespielt_set:
                    break
                idx += 1
            if idx >= len(unmatched):
                idx = 0  # Alle verbleibenden sind Rematches → ersten nehmen
        t2 = unmatched.pop(idx)
        result.append((t1, t2))
    return result


def spieltag_runde_generieren(spieltag_id):
    """Generiert dynamisch die nächste Runde für den Americano-Modus."""
    conn = verbindung()

    alle = [dict(m) for m in conn.execute(
        "SELECT * FROM matches WHERE spieltag_id=?", (spieltag_id,)
    ).fetchall()]

    # Bestehende Paarungen für Rematch-Erkennung
    gespielt_set = set()
    for m in alle:
        k1 = frozenset([m['team1_s1_id'], m['team1_s2_id']])
        k2 = frozenset([m['team2_s1_id'], m['team2_s2_id']])
        gespielt_set.add(frozenset([k1, k2]))

    # Alle bekannten 2er-Teams aus bisherigen Matches (inkl. solche mit 0 Punkten)
    alle_team_keys = set()
    for m in alle:
        alle_team_keys.add(tuple(sorted([m['team1_s1_id'], m['team1_s2_id']])))
        alle_team_keys.add(tuple(sorted([m['team2_s1_id'], m['team2_s2_id']])))

    # Spieltag-Punkte pro 2er-Team berechnen
    punkte = {k: {'punkte': 0, 'siege': 0} for k in alle_team_keys}
    for m in alle:
        if m['status'] != 'gespielt':
            continue
        t1_tore, t2_tore = int(m['tore_team1']), int(m['tore_team2'])
        if t1_tore > t2_tore:   p1, p2, s1, s2 = 3, 0, 1, 0
        elif t2_tore > t1_tore: p1, p2, s1, s2 = 0, 3, 0, 1
        else:                    p1, p2, s1, s2 = 1, 1, 0, 0
        key1 = tuple(sorted([m['team1_s1_id'], m['team1_s2_id']]))
        key2 = tuple(sorted([m['team2_s1_id'], m['team2_s2_id']]))
        punkte[key1]['punkte'] += p1
        punkte[key1]['siege']  += s1
        punkte[key2]['punkte'] += p2
        punkte[key2]['siege']  += s2

    # Absteigend sortiert nach Spieltag-Punkten, dann Siegen
    sortiert = sorted(alle_team_keys,
                      key=lambda k: (punkte[k]['punkte'], punkte[k]['siege']),
                      reverse=True)

    aktuelle_runde = conn.execute(
        "SELECT aktuelle_runde FROM spieltage WHERE id=?", (spieltag_id,)
    ).fetchone()[0]
    naechste_runde = aktuelle_runde + 1

    paarungen = _americano_paarungen(sortiert, gespielt_set, gewinner_vs_verlierer=True)

    for (t1, t2) in paarungen:
        mid = str(uuid.uuid4())[:8]
        conn.execute("""
            INSERT INTO matches
            (id, spieltag_id, runde, team1_s1_id, team1_s2_id, team2_s1_id, team2_s2_id)
            VALUES (?,?,?,?,?,?,?)
        """, (mid, spieltag_id, naechste_runde, t1[0], t1[1], t2[0], t2[1]))

    conn.commit()
    conn.close()


# ══ Admin & Plus ═══════════════════════════════════════════════════

def account_ist_admin(account_id, team_id):
    conn = verbindung()
    row = conn.execute(
        "SELECT admin_account_id FROM teams WHERE id=?",
        (team_id,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    return row['admin_account_id'] == account_id


def team_ist_plus(team_id):
    conn = verbindung()
    row = conn.execute(
        "SELECT ist_plus, admin_account_id FROM teams WHERE id=?",
        (team_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row['ist_plus']:
        conn.close()
        return True
    if row['admin_account_id']:
        verein = conn.execute(
            "SELECT hat_vereinsabo, vereinsabo_bis FROM accounts WHERE id=?",
            (row['admin_account_id'],)
        ).fetchone()
        conn.close()
        if verein and verein['hat_vereinsabo']:
            bis = verein['vereinsabo_bis']
            if bis is None or bis > datetime.utcnow().strftime('%Y-%m-%d'):
                return True
        return False
    conn.close()
    return False


def team_admin_aendern(team_id, neuer_admin_account_id):
    conn = verbindung()
    mitglied = conn.execute(
        "SELECT account_id FROM account_team WHERE account_id=? AND team_id=?",
        (neuer_admin_account_id, team_id)
    ).fetchone()
    if not mitglied:
        conn.close()
        return False, "Neuer Admin muss bereits Mitglied sein"
    conn.execute("UPDATE account_team SET ist_admin=0 WHERE team_id=?", (team_id,))
    conn.execute(
        "UPDATE account_team SET ist_admin=1 WHERE account_id=? AND team_id=?",
        (neuer_admin_account_id, team_id)
    )
    conn.execute(
        "UPDATE teams SET admin_account_id=? WHERE id=?",
        (neuer_admin_account_id, team_id)
    )
    conn.commit()
    conn.close()
    return True, None


def team_mitglieder_accounts(team_id):
    conn = verbindung()
    rows = conn.execute(
        """SELECT a.id, a.alias, at.ist_admin
           FROM account_team at
           JOIN accounts a ON a.id = at.account_id
           WHERE at.team_id=?
           ORDER BY at.ist_admin DESC, a.alias ASC""",
        (team_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def admin_statistiken():
    conn = verbindung()

    gesamt_accounts  = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    gesamt_teams     = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    plus_teams       = conn.execute("""
        SELECT COUNT(*) FROM teams t
        WHERE t.ist_plus = 1
        OR EXISTS (
            SELECT 1 FROM accounts a
            WHERE a.id = t.admin_account_id
            AND a.hat_vereinsabo = 1
            AND (a.vereinsabo_bis IS NULL OR a.vereinsabo_bis > date('now'))
        )
    """).fetchone()[0]
    verein_accounts  = conn.execute("""
        SELECT COUNT(*) FROM accounts
        WHERE hat_vereinsabo = 1
        AND (vereinsabo_bis IS NULL OR vereinsabo_bis > date('now'))
    """).fetchone()[0]
    aktive_spieltage = conn.execute("SELECT COUNT(*) FROM spieltage WHERE status='aktiv'").fetchone()[0]
    gesamt_matches   = conn.execute("SELECT COUNT(*) FROM matches WHERE status='gespielt'").fetchone()[0]

    neue_accounts_woche = conn.execute("""
        SELECT COUNT(*) FROM accounts
        WHERE erstellt_am >= datetime('now', '-7 days')
    """).fetchone()[0]

    neue_teams_woche = conn.execute("""
        SELECT COUNT(*) FROM teams
        WHERE erstellt_am >= datetime('now', '-7 days')
    """).fetchone()[0]

    mitglieder_verteilung = conn.execute("""
        SELECT spieler_anzahl, gaeste_anzahl, COUNT(*) as anzahl_teams
        FROM (
            SELECT t.id,
                COUNT(CASE WHEN s.ist_gast = 0 THEN 1 END) as spieler_anzahl,
                COUNT(CASE WHEN s.ist_gast = 1 THEN 1 END) as gaeste_anzahl
            FROM teams t
            LEFT JOIN spieler s ON s.team_id = t.id
            GROUP BY t.id
        )
        GROUP BY spieler_anzahl, gaeste_anzahl
        ORDER BY spieler_anzahl + gaeste_anzahl DESC, spieler_anzahl DESC
    """).fetchall()

    registrierungen_verlauf = conn.execute("""
        SELECT DATE(erstellt_am) as datum, COUNT(*) as anzahl
        FROM accounts
        WHERE erstellt_am >= datetime('now', '-30 days')
        GROUP BY DATE(erstellt_am)
        ORDER BY datum ASC
    """).fetchall()

    teams_verlauf = conn.execute("""
        SELECT DATE(erstellt_am) as datum, COUNT(*) as anzahl
        FROM teams
        WHERE erstellt_am >= datetime('now', '-30 days')
        GROUP BY DATE(erstellt_am)
        ORDER BY datum ASC
    """).fetchall()

    conn.close()

    return {
        "gesamt": {
            "accounts": gesamt_accounts,
            "teams": gesamt_teams,
            "plus_teams": plus_teams,
            "free_teams": gesamt_teams - plus_teams,
            "verein_accounts": verein_accounts,
            "aktive_spieltage": aktive_spieltage,
            "gesamt_matches": gesamt_matches,
        },
        "diese_woche": {
            "neue_accounts": neue_accounts_woche,
            "neue_teams": neue_teams_woche,
        },
        "verlauf": {
            "registrierungen": [dict(r) for r in registrierungen_verlauf],
            "teams": [dict(r) for r in teams_verlauf],
        },
        "mitglieder_verteilung": [dict(r) for r in mitglieder_verteilung],
    }

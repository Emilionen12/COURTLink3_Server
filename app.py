"""
app.py — Court Link Flask Backend MOIN moin moin
"""
import os

from flask import Flask, render_template, request, jsonify, session
from datenbank import (
    initialisiere_db,
    team_erstellen, team_per_code, team_per_id, team_passwort_pruefen,
    spieler_registrieren, spieler_als_gast, gast_uebernehmen,
    spieler_des_teams, spieler_loeschen, spieler_claim_code,
    spieltag_erstellen, spieltag_matches, ergebnis_eintragen,
    ergebnisse_eintragen_bulk,
    spieltag_beenden, aktiver_spieltag, ranking,
    spieltag_archiv_alle, spieltag_team_ranking,
    account_registrieren, account_einloggen, account_per_id,
    account_teams, account_stats_aktualisieren,
    account_team_verknuepfen, team_beitreten,
)
import secrets

app = Flask(__name__)
#app.secret_key = secrets.token_hex(16)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
initialisiere_db()


def team_id():    return session.get('team_id')
def spieler_id(): return session.get('spieler_id')
def account_id(): return session.get('account_id')


@app.route("/")
def index():
    return render_template("index.html")

# ══ Account registrieren / einloggen ═══════════════════════════════

@app.route("/api/account/registrieren", methods=["POST"])
def api_account_registrieren():
    d       = request.get_json()
    name    = d.get("name", "").strip()
    passwort = d.get("passwort", "")
    if not name or not passwort:
        return jsonify({"fehler": "Name und Passwort sind Pflicht"}), 400
    if len(passwort) < 4:
        return jsonify({"fehler": "Passwort mind. 4 Zeichen"}), 400
    acc, fehler = account_registrieren(name, passwort)
    if fehler:
        return jsonify({"fehler": fehler}), 400
    session['account_id'] = acc['id']
    session.pop('team_id', None)
    session.pop('spieler_id', None)
    return jsonify({"account": acc, "teams": []})


@app.route("/api/account/einloggen", methods=["POST"])
def api_account_einloggen():
    d       = request.get_json()
    name    = d.get("name", "").strip()
    passwort = d.get("passwort", "")
    if not name or not passwort:
        return jsonify({"fehler": "Name und Passwort sind Pflicht"}), 400
    acc, fehler = account_einloggen(name, passwort)
    if fehler:
        return jsonify({"fehler": fehler}), 401
    session['account_id'] = acc['id']
    session.pop('team_id', None)
    session.pop('spieler_id', None)
    teams = account_teams(acc['id'])
    return jsonify({"account": acc, "teams": teams})


@app.route("/api/account/info")
def api_account_info():
    aid = account_id()
    if not aid:
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    acc   = account_per_id(aid)
    teams = account_teams(aid)
    stats = account_stats_aktualisieren(aid)
    return jsonify({"account": acc, "teams": teams, "stats": stats})


# ══ Team erstellen ══════════════════════════════════════════════════

@app.route("/api/team/erstellen", methods=["POST"])
def api_team_erstellen():
    if not account_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d         = request.get_json()
    team_name = d.get("team_name", "").strip()
    team_pw   = d.get("team_passwort", "")
    name      = d.get("spieler_name", "").strip()
    alias     = d.get("alias", "").strip()

    if not team_name or not team_pw or not name:
        return jsonify({"fehler": "Alle Pflichtfelder ausfüllen"}), 400
    if len(team_pw) < 4:
        return jsonify({"fehler": "Team-Passwort mind. 4 Zeichen"}), 400

    team    = team_erstellen(team_name, team_pw)
    spieler, fehler = spieler_registrieren(name, alias, str(__import__('uuid').uuid4()), team['id'])
    if fehler:
        return jsonify({"fehler": fehler}), 400

    account_team_verknuepfen(account_id(), team['id'], spieler['id'])
    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Team beitreten ══════════════════════════════════════════════════

@app.route("/api/team/beitreten", methods=["POST"])
def api_team_beitreten():
    if not account_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d       = request.get_json()
    code    = d.get("code", "").strip()
    team_pw = d.get("team_passwort", "")
    name    = d.get("spieler_name", "").strip()
    alias   = d.get("alias", "").strip()

    if not code or not team_pw:
        return jsonify({"fehler": "Team-Code und Passwort sind Pflicht"}), 400

    team, spieler, fehler = team_beitreten(account_id(), code, team_pw, name, alias)
    if fehler:
        return jsonify({"fehler": fehler}), 400

    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Gast übernehmen ═════════════════════════════════════════════════

@app.route("/api/gast/uebernehmen", methods=["POST"])
def api_gast_uebernehmen():
    if not account_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d          = request.get_json()
    claim_code = d.get("claim_code", "").strip()
    if not claim_code:
        return jsonify({"fehler": "Claim-Code ist Pflicht"}), 400

    team, spieler, fehler = gast_uebernehmen(claim_code, account_id())
    if fehler:
        return jsonify({"fehler": fehler}), 400

    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Team wechseln ════════════════════════════════════════════════════

@app.route("/api/team/verlassen", methods=["POST"])
def api_team_verlassen():
    session.pop('team_id', None)
    session.pop('spieler_id', None)
    return jsonify({"ok": True})


@app.route("/api/team/waehlen", methods=["POST"])
def api_team_waehlen():
    if not account_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d   = request.get_json()
    tid = d.get("team_id", "")
    teams = account_teams(account_id())
    match = next((t for t in teams if t['id'] == tid), None)
    if not match:
        return jsonify({"fehler": "Team nicht gefunden oder kein Zugriff"}), 403
    session['team_id']    = match['id']
    session['spieler_id'] = match['spieler_id']
    return jsonify({"team": team_per_id(match['id'])})


# ══ Session / Abmelden ══════════════════════════════════════════════

@app.route("/api/session")
def api_session():
    aid = account_id()
    if not aid:
        return jsonify({"eingeloggt": False})
    tid = team_id()
    return jsonify({
        "eingeloggt": True,
        "account":    account_per_id(aid),
        "team":       team_per_id(tid) if tid else None,
        "spieler_id": spieler_id(),
        "teams":      account_teams(aid),
    })


@app.route("/api/abmelden", methods=["POST"])
def api_abmelden():
    session.clear()
    return jsonify({"ok": True})


# ══ Spieler ════════════════════════════════════════════════════════

@app.route("/api/spieler")
def api_spieler_liste():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    return jsonify(spieler_des_teams(team_id()))


@app.route("/api/spieler", methods=["POST"])
def api_spieler_add():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d     = request.get_json()
    name  = d.get("name", "").strip()
    alias = d.get("alias", "").strip()
    if not name: return jsonify({"fehler": "Name darf nicht leer sein"}), 400
    spieler, fehler = spieler_als_gast(name, alias, team_id())
    if fehler: return jsonify({"fehler": fehler}), 400
    return jsonify(spieler), 201


@app.route("/api/spieler/<sid>", methods=["DELETE"])
def api_spieler_del(sid):
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    spieler_loeschen(sid, team_id())
    return jsonify({"ok": True})


@app.route("/api/spieler/<sid>/claim_code")
def api_claim_code(sid):
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    daten = spieler_claim_code(sid, team_id())
    if not daten: return jsonify({"fehler": "Kein Code gefunden"}), 404
    return jsonify(daten)


# ══ Ranking ════════════════════════════════════════════════════════

@app.route("/api/ranking")
def api_ranking():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    return jsonify(ranking(team_id()))


# ══ Spieltag ═══════════════════════════════════════════════════════

@app.route("/api/spieltag/aktiv")
def api_spieltag_aktiv():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    st = aktiver_spieltag(team_id())
    if not st: return jsonify({"aktiv": False})
    return jsonify({"aktiv": True, "spieltag": st})


@app.route("/api/spieltag/starten", methods=["POST"])
def api_spieltag_starten():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d = request.get_json()
    spieltag, fehler = spieltag_erstellen(
        team_id(), d.get("modus", "random"), d.get("spieler_ids", [])
    )
    if fehler: return jsonify({"fehler": fehler}), 400
    return jsonify(spieltag)


@app.route("/api/spieltag/ergebnis", methods=["POST"])
def api_ergebnis():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d = request.get_json()
    # Akzeptiert einzelnes Objekt ODER Liste — alles wird atomar gespeichert
    if isinstance(d, list):
        ergebnisse = d
    else:
        ergebnisse = [d]
    try:
        naechste = ergebnisse_eintragen_bulk(ergebnisse)
    except ValueError as e:
        return jsonify({"fehler": str(e)}), 400
    return jsonify({"ok": True, "naechste_runde": naechste})


@app.route("/api/spieltag/beenden", methods=["POST"])
def api_spieltag_beenden():
    if not team_id(): return jsonify({"fehler": "Nicht eingeloggt"}), 401
    d = request.get_json()
    spieltag_beenden(d['spieltag_id'])
    return jsonify({"ok": True})

@app.route("/api/spieltag/<st_id>/team_ranking")
def api_spieltag_team_ranking(st_id):
    if not team_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    return jsonify(spieltag_team_ranking(st_id))


@app.route("/api/spieltag/archiv")
def api_spieltag_archiv():
    if not team_id():
        return jsonify({"fehler": "Nicht eingeloggt"}), 401
    return jsonify(spieltag_archiv_alle(team_id()))



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

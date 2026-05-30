"""
app.py — Court Link Flask Backend MOIN moin moin
"""
import os

from flask import Flask, render_template, request, jsonify, session
from datenbank import (
    initialisiere_db,
    team_erstellen, team_per_code, team_per_id, team_passwort_pruefen,
    spieler_registrieren, spieler_einloggen,
    spieler_als_gast, gast_uebernehmen,
    spieler_des_teams, spieler_loeschen, spieler_claim_code,
    spieltag_erstellen, spieltag_matches, ergebnis_eintragen,
    spieltag_beenden, aktiver_spieltag, ranking
)
import secrets

app = Flask(__name__)
#app.secret_key = secrets.token_hex(16)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
initialisiere_db()


def team_id():   return session.get('team_id')
def spieler_id(): return session.get('spieler_id')


@app.route("/")
def index():
    return render_template("index.html")

#spieltag_team_ranking
# ══ Team erstellen ══════════════════════════════════════════════════

@app.route("/api/team/erstellen", methods=["POST"])
def api_team_erstellen():
    d            = request.get_json()
    team_name    = d.get("team_name", "").strip()
    team_pw      = d.get("team_passwort", "")
    name         = d.get("spieler_name", "").strip()
    alias        = d.get("alias", "").strip()
    spieler_pw   = d.get("passwort", "")

    if not team_name or not team_pw or not name or not spieler_pw:
        return jsonify({"fehler": "Alle Pflichtfelder ausfüllen"}), 400
    if len(team_pw) < 4:
        return jsonify({"fehler": "Team-Passwort mind. 4 Zeichen"}), 400
    if len(spieler_pw) < 4:
        return jsonify({"fehler": "Account-Passwort mind. 4 Zeichen"}), 400

    team = team_erstellen(team_name, team_pw)
    spieler, fehler = spieler_registrieren(name, alias, spieler_pw, team['id'])
    if fehler:
        return jsonify({"fehler": fehler}), 400

    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Einloggen (bestehender Account) ════════════════════════════════

@app.route("/api/einloggen", methods=["POST"])
def api_einloggen():
    d          = request.get_json()
    code       = d.get("code", "").strip()
    team_pw    = d.get("team_passwort", "")
    name       = d.get("spieler_name", "").strip()
    spieler_pw = d.get("passwort", "")

    if not code or not team_pw or not name or not spieler_pw:
        return jsonify({"fehler": "Alle Felder ausfüllen"}), 400

    team = team_per_code(code)
    if not team:
        return jsonify({"fehler": "Team nicht gefunden"}), 404
    if not team_passwort_pruefen(team, team_pw):
        return jsonify({"fehler": "Team-Passwort falsch"}), 401

    spieler, fehler = spieler_einloggen(name, spieler_pw, team['id'])
    if fehler:
        return jsonify({"fehler": fehler}), 401

    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Team beitreten (neuer Account) ═════════════════════════════════

@app.route("/api/team/beitreten", methods=["POST"])
def api_team_beitreten():
    d          = request.get_json()
    code       = d.get("code", "").strip()
    team_pw    = d.get("team_passwort", "")
    name       = d.get("spieler_name", "").strip()
    alias      = d.get("alias", "").strip()
    spieler_pw = d.get("passwort", "")

    if not code or not team_pw or not name or not spieler_pw:
        return jsonify({"fehler": "Alle Felder ausfüllen"}), 400
    if len(spieler_pw) < 4:
        return jsonify({"fehler": "Account-Passwort mind. 4 Zeichen"}), 400

    team = team_per_code(code)
    if not team:
        return jsonify({"fehler": "Team nicht gefunden"}), 404
    if not team_passwort_pruefen(team, team_pw):
        return jsonify({"fehler": "Team-Passwort falsch"}), 401

    spieler, fehler = spieler_registrieren(name, alias, spieler_pw, team['id'])
    if fehler:
        return jsonify({"fehler": fehler}), 400

    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Gast-Account übernehmen ════════════════════════════════════════

@app.route("/api/gast/uebernehmen", methods=["POST"])
def api_gast_uebernehmen():
    d          = request.get_json()
    claim_code = d.get("claim_code", "").strip()
    name       = d.get("spieler_name", "").strip()
    alias      = d.get("alias", "").strip()
    spieler_pw = d.get("passwort", "")

    if not claim_code or not name or not spieler_pw:
        return jsonify({"fehler": "Code, Name und Passwort sind Pflicht"}), 400
    if len(spieler_pw) < 4:
        return jsonify({"fehler": "Passwort mind. 4 Zeichen"}), 400

    spieler, fehler = gast_uebernehmen(claim_code, name, alias, spieler_pw)
    if fehler:
        return jsonify({"fehler": fehler}), 400

    team = team_per_id(spieler['team_id'])
    session['team_id']    = team['id']
    session['spieler_id'] = spieler['id']
    return jsonify({"team": team, "spieler": spieler})


# ══ Session / Abmelden ══════════════════════════════════════════════

@app.route("/api/session")
def api_session():
    tid = team_id()
    if not tid:
        return jsonify({"eingeloggt": False})
    return jsonify({"eingeloggt": True, "team": team_per_id(tid), "spieler_id": spieler_id()})


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
    naechste = ergebnis_eintragen(d['match_id'], int(d['tore_team1']), int(d['tore_team2']))
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
    from datenbank import spieltag_team_ranking
    return jsonify(spieltag_team_ranking(st_id))



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

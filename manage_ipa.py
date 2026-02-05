#!/usr/bin/env python3
# Author: Arttumiro
# FreeIPA Luokkahallinta — Batch + Case optimized

import re
import os
from datetime import datetime
from ipalib import api, errors

LOGFILE = "ipa_luokkahallinta.log"
MAX_LOGS = 10


# ---------------- LOGGING ----------------
def write_log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}\n"

    lines = []
    if os.path.exists(LOGFILE):
        with open(LOGFILE, "r") as f:
            lines = f.readlines()

    lines.append(entry)
    lines = lines[-MAX_LOGS:]

    with open(LOGFILE, "w") as f:
        f.writelines(lines)


# ---------------- IPA INIT ----------------
def init_ipa():
    try:
        api.bootstrap(context="cli")
        api.finalize()
        api.Backend.rpcclient.connect()
    except Exception:
        print("Virhe: Kerberos / IPA ei käytettävissä")
        print("Suorita: kinit admin")
        exit(1)


init_ipa()


# ---------------- HELPERS ----------------
def sanitize_group_name(name):
    return name.lower().replace("ä", "a").replace("ö", "o")


def normalize_uid(uid):
    uid = uid.strip()
    if re.fullmatch(r"[0-9]{6}", uid):
        return "o" + uid
    if re.fullmatch(r"o[0-9]{6}", uid):
        return uid
    return None


def validate_group_name(group):
    return re.fullmatch(r"s[0-9]{2}[a-z]{4}", group)


# ---------------- CREATE GROUP ----------------
def create_group():
    raw = input("Luokan nimike: ").strip()
    if not raw:
        print("Virhe: tyhjä nimi")
        return

    group = sanitize_group_name(raw)

    if not validate_group_name(group):
        print("Virhe: väärä ryhmän muoto")
        return

    try:
        api.Command.group_show(group)
        print("Ryhmää ei luotu — jo olemassa")
        return
    except errors.NotFound:
        pass

    api.Command.group_add(group, description=f"Ryhmä luokalle {group}")
    print(f"Luokka luotu: {group}")
    write_log(f"Luotiin ryhmä {group}")


# ---------------- CREATE USER ----------------
def create_user():
    raw = input("Oppilastunnus (231054 / o231054): ").strip()
    uid = normalize_uid(raw)

    if not uid:
        print("Virhe: tunnus väärin")
        return

    try:
        api.Command.user_show(uid)
        print("Käyttäjä on jo olemassa")
        return
    except errors.NotFound:
        pass

    fname = input("Etunimi: ").strip()
    lname = input("Sukunimi: ").strip()

    if not fname or not lname:
        print("Virhe: nimi puuttuu")
        return

    api.Command.user_add(uid, givenname=fname, sn=lname, userpassword="changeme")

    print(f"Käyttäjä luotu: {uid} (salasana: changeme)")
    write_log(f"Luotiin käyttäjä {uid}")

    if input("Lisätäänkö luokkaan? (k/e): ").lower() == "k":
        group = sanitize_group_name(input("Luokan nimi: "))

        try:
            api.Command.group_add_member(group, user=[uid])
            print(f"Käyttäjä lisätty ryhmään {group}")
            write_log(f"{uid} lisätty ryhmään {group}")
        except errors.NotFound:
            print("Ryhmää ei ole")


# ---------------- ADD USERS TO GROUP (FULL BATCH) ----------------
def add_users_to_group():
    raw = input("Oppilastunnukset pilkulla erotettuna: ")
    group = sanitize_group_name(input("Luokan nimi: "))

    if not validate_group_name(group):
        print("Virhe: väärä ryhmän muoto")
        return

    raw_users = raw.replace(",", " ").split()

    normalized = []
    skipped = []

    for u in raw_users:
        uid = normalize_uid(u)
        if uid:
            normalized.append(uid)
        else:
            skipped.append(f"{u} (virheellinen)")

    if not normalized:
        print("Ei kelvollisia käyttäjiä")
        return

    # ---- Batch: user existence check ----
    batch_check = [
        ("user_show", [uid], {}) for uid in normalized
    ]
    check_result = api.Command.batch(batch_check)

    existing = []
    for uid, res in zip(normalized, check_result["results"]):
        if "error" in res:
            skipped.append(f"{uid} (ei ole)")
        else:
            existing.append(uid)

    if not existing:
        print("Ei lisättäviä käyttäjiä")
        return

    # ---- Batch: group add ----
    batch_add = [
        ("group_add_member", [group], {"user": [uid]})
        for uid in existing
    ]
    add_result = api.Command.batch(batch_add)

    added = []
    for uid, res in zip(existing, add_result["results"]):
        if "error" in res:
            skipped.append(f"{uid} (jo jäsen)")
        else:
            added.append(uid)

    print("------------------------------------------------")
    print("Luokka:", group)
    if added:
        print("Lisätty:", ", ".join(added))
        write_log(f"LISÄTTY RYHMÄÄN {group}: {', '.join(added)}")
    if skipped:
        print("Ohitetut:", ", ".join(skipped))
    print("------------------------------------------------")

    write_log(f"Batch: {len(added)} käyttäjää lisätty ryhmään {group}")


# ---------------- LIST GROUPS (BATCH) ----------------
def list_groups():
    result = api.Command.group_find()

    print("Luokat:")
    groups = [
        g["cn"][0]
        for g in result["result"]
        if validate_group_name(g["cn"][0])
    ]

    for g in sorted(groups):
        print(g)


# ---------------- LIST USERS (BATCH + FILTER) ----------------
def list_users():
    group_filter = None

    if input("Rajataanko luokan mukaan? (k/e): ").lower() == "k":
        group = sanitize_group_name(input("Luokan nimi: "))

        try:
            data = api.Command.group_show(group)
            group_filter = set(data["result"].get("member_user", []))
        except errors.NotFound:
            print("Ryhmää ei ole — näytetään kaikki")

    users = api.Command.user_find(all=True)

    print("------------------------------------------------")
    print("{:<15} {:<20} {:<20}".format("Tunnus", "Etunimi", "Sukunimi"))
    print("------------------------------------------------")

    for u in users["result"]:
        uid = u["uid"][0]

        if not re.fullmatch(r"o[0-9]{6}", uid):
            continue

        if group_filter and uid not in group_filter:
            continue

        fname = u.get("givenname", [""])[0]
        lname = u.get("sn", [""])[0]

        print("{:<15} {:<20} {:<20}".format(uid, fname, lname))

    print("------------------------------------------------")


# ---------------- MENU ----------------
def show_menu():
    print("\n=============================")
    print("   FreeIPA Luokkahallinta")
    print("=============================")
    print("1) Uusi luokka")
    print("2) Uusi oppilas")
    print("3) Lisää oppilaita luokkaan (BATCH)")
    print("4) Listaa luokat")
    print("5) Listaa oppilaat")
    print("6) Poistu")


# ---------------- MAIN LOOP (CASE) ----------------
while True:
    show_menu()
    choice = input("Valitse [1-6]: ").strip()

    match choice:
        case "1":
            create_group()

        case "2":
            create_user()

        case "3":
            add_users_to_group()

        case "4":
            list_groups()

        case "5":
            list_users()

        case "6":
            print("Valmis!")
            break

        case _:
            print("Virheellinen valinta")


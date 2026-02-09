#!/usr/bin/env python3
# Author: Arttumiro
# FreeIPA Luokkahallinta

#Lisää Regex tuen
import re

#Parempi normalisointi
import unicodedata

import os
from datetime import datetime
from ipalib import api, errors

LOGFILE = "ipa_luokkahallinta.log"
#Varmistaa, ettei logitiedosto vie liian paljon tilaa, mutta silti hyödyllinen
MAX_LOGS = 200

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

# Jos suoritetaan palvelimella, ei tarvitse Kerberos tikettiä tai rpc yhteyttä
def init_ipa():
    server_check = os.path.exists("/etc/ipa/server.conf")
    try:
        if server_check:
            if os.geteuid() != 0:
                raise PermissionError("Root-oikeudet vaaditaan FreeIPA-palvelimella.")

            api.bootstrap(context="server")
            api.finalize()
            api.Backend.ldap2.connect()
        else:
            api.bootstrap(context="cli")
            api.finalize()
            try:
                api.Backend.rpcclient.connect()
            except errors.ACIError:
                raise PermissionError("Kerberos-tiketin käyttöoikeudet eivät riitä. Suorita 'kinit admin'.")
            except errors.KerberosError:
                raise PermissionError("Kerberos-tiketti puuttuu. Suorita 'kinit admin'.")
            except Exception as e:
                raise RuntimeError(f"Yhteysvirhe: {e}")

    except PermissionError as e:
        print(f"Virhe: {e}")
        exit(1)

    except Exception as e:
        print(f"Odottamaton virhe: {e}")
        exit(1)

init_ipa()

# Helper Functions
def sanitize_class_name(name):
    # Muuta pieniksi kirjaimiksi
    name = name.lower()

    # Poista aksentit ja skandit (ä > a, ö > o, å > a)
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()

    # Poista kaikki muut kuin a–z ja numerot
    name = re.sub(r"[^a-z0-9]", "", name)

    return name

def normalize_uid(uid):
    uid = uid.strip()
    if re.fullmatch(r"[0-9]{6}", uid):
        return "o" + uid
    if re.fullmatch(r"o[0-9]{6}", uid):
        return uid
    return None

def validate_class_name(group):
    return re.fullmatch(r"s[0-9]{2}[a-z]{4}", group)

def get_group_users(group):
    data = api.Command.group_show(group)
    result = data["result"]

    users = set()

    # Suorat käyttäjät
    for uid in result.get("member_user") or []:
        users.add(uid)

    # Epäsuorat käyttäjät
    for uid in result.get("memberindirect_user") or []:
        users.add(uid)

    return users

def create_class():
    raw = input("Luokan nimi (esim. s23ätiv): ").strip()
    if not raw:
        print("Virhe: Tyhjä nimi")
        return

    group = sanitize_class_name(raw)

    if not validate_class_name(group):
        print("Virhe: Luokan nimi väärässä muodossa")
        return

    try:
        api.Command.group_show(group)
        print("Virhe: Ryhmää ei luotu, luokka on jo olemassa")
        return
    except errors.NotFound:
        pass

    try:
        api.Command.group_add(group, description=f"Ryhmä luokalle {group}")
        print(f"Luokka luotu: {group}")
        write_log(f"Luotiin ryhmä {group}")
    except Exception as e:
        print(f"Virhe luodessa luokkaa: {e}")

def create_student():
    raw = input("Oppilastunnus (231054 / o231054): ").strip()
    uid = normalize_uid(raw)

    if not uid:
        print("Virhe: Tunnus väärin")
        return

    try:
        api.Command.user_show(uid)
        print("Virhe: Käyttäjä on jo olemassa")
        return
    except errors.NotFound:
        pass

    fname = input("Etunimi: ").strip()
    lname = input("Sukunimi: ").strip()

    if not fname or not lname:
        if not fname:
            print ("Virhe: Etunimi puuttuu")
        else:
            print("Virhe: Sukunimi puuttuu")
        return

    try:
        api.Command.user_add(uid, givenname=fname, sn=lname,
                             cn=f"{fname} {lname}", userpassword="changeme")
        print(f"Käyttäjä luotu: {uid} (salasana: changeme)")
        write_log(f"Luotiin käyttäjä {uid}")
    except Exception as e:
        print(f"Virhe käyttäjän luonnissa: {e}")
        return

    if input("Lisätäänkö luokkaan? (k/e): ").strip().lower() == "k":
        group = sanitize_class_name(input("Luokan nimi (esim. s23ätiv: ").strip())
        try:
            api.Command.group_add_member(group, user=[uid])
            print(f"Käyttäjä lisätty luokkaan {group}")
            write_log(f"{uid} lisätty luokkaan {group}")
        except Exception as e:
            print(f"Virhe lisättäessä luokkaan: {e}")

def add_students_to_class():
    raw = input("Oppilastunnukset pilkuilla tai välilyönneillä erotettuna: ")
    group = sanitize_class_name(input("Luokan nimi (esim. s23ätiv): ").strip())

    if not validate_class_name(group):
        print("Virhe: Väärä luokan muoto")
        return

    raw_users = raw.replace(",", " ").split()

    normalized = []
    skipped = []

    for u in raw_users:
        uid = normalize_uid(u)
        if uid:
            normalized.append(uid)
        else:
            skipped.append(f"{u} (virheellinen oppilastunnus)")

    if not normalized:
        print(f"Virhe: {', '.join(skipped)}")
        return

    # Make sure Student exists
    batch_check = [
        {"method": "user_show", "params": [[uid], {}]} 
        for uid in normalized
    ]
    check_result = api.Command.batch(batch_check)

    students = []
    for uid, res in zip(normalized, check_result["results"]):
        if res.get("error"):
            skipped.append(f"{uid} (käyttäjää ei ole)")
        else:
            students.append(uid)

    if not students:
        print(f"Virhe: {', '.join(skipped)}")
        return

    # Get current Students in Class
    current_members = get_group_users(group)

    to_add = [uid for uid in students if uid not in current_members]
    already_in_group = [uid for uid in students if uid in current_members]

    # Only add new users
    added = []
    if to_add:
        batch_add = [{"method": "group_add_member", "params": [[group], {"user": [uid]}]} for uid in to_add]
        add_result = api.Command.batch(batch_add)

        for uid, res in zip(to_add, add_result["results"]):
            if res.get("error"):
                skipped.append(f"{uid} (lisäys epäonnistui)")
            else:
                added.append(uid)

    skipped.extend([f"{uid} (jo jäsen)" for uid in already_in_group])

    print("------------------------------------------------")
    print("Luokka:", group)
    if added:
        print(f"Lisätty: {', '.join(added)}")
        write_log(f"Lisätty luokkaan {group}: {', '.join(added)}")
    if skipped:
        print(f"Ohitetut: {', '.join(skipped)}")
        write_log(f"Ohitetut: {', '.join(skipped)}")
    print("------------------------------------------------")

    write_log(f"{len(added)} käyttäjää lisätty luokkaan {group}")
    write_log(f"{len(skipped)} käyttäjän lisääminen epäonnistunut luokkaan {group}")

def list_classes():
    result = api.Command.group_find()

    print("Luokat:")
    groups = [
        g["cn"][0]
        for g in result["result"]
        if validate_class_name(g["cn"][0])
    ]

    for g in sorted(groups):
        print(g)

def list_students():
    group_filter = None

    if input("Rajataanko luokan mukaan? (k/e): ").strip().lower() == "k":
        group = sanitize_class_name(input("Luokan nimi (esim. s23ätiv): ").strip())

        try:
            group_filter = get_group_users(group)

            if not group_filter:
                print("Virhe: Ryhmässä ei löytynyt käyttäjiä")
                return

        except errors.NotFound:
            print(f"Virhe: Luokkaa {group} ei ole")
            return

    users = api.Command.user_find(all=True, sizelimit=0)

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

def show_menu():
    print("\n=============================")
    print("   FreeIPA Luokkahallinta")
    print("=============================")
    print("1) Uusi luokka")
    print("2) Uusi oppilas")
    print("3) Lisää oppilaita luokkaan")
    print("4) Listaa luokat")
    print("5) Listaa oppilaat")
    print("6) Poistu")

# Menu loop
while True:
    show_menu()
    choice = input("Valitse [1-6]: ").strip()

    match choice:
        case "1":
            create_class()

        case "2":
            create_student()

        case "3":
            add_students_to_class()

        case "4":
            list_classes()

        case "5":
            list_students()

        case "6":
            print("Valmis!")
            break

        case _:
            print("Virheellinen valinta")


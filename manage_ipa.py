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
    print("Käynnistyy...")
    server_check = os.path.exists("/etc/ipa/server.conf")
    try:
        if server_check:
            if os.geteuid() != 0:
                raise PermissionError("Root-oikeudet vaaditaan FreeIPA-palvelimella. (sudo)")
                
            api.bootstrap(context="server")
            api.finalize()
            api.Backend.ldap2.connect()
            print("Valmis!")
        else:
            api.bootstrap(context="cli")
            api.finalize()
            try:
                api.Backend.rpcclient.connect()
                print("Valmis!")

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

# Helpperi funktiot

# Regex kompilaatio
UID_RE = re.compile(r"o[0-9]{6}")
RAW_UID_RE = re.compile(r"[0-9]{6}")
CLASS_RE = re.compile(r"s[0-9]{2}[a-z]{4}")

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
    if UID_RE.fullmatch(uid):
        return uid
    if RAW_UID_RE.fullmatch(uid):
        return "o" + uid
    return None

def validate_class_name(group):
    return bool(CLASS_RE.fullmatch(group))


# Pää funktiot

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
        api.Command.group_add(group, description=f"Ryhmä luokalle {group}")
        print(f"Ryhmä luotu luokalle: {group}")
        write_log(f"Luotiin ryhmä luokalle {group}")
        
    except errors.DuplicateEntry:
        print("Virhe: Luokka on jo olemassa")
        return
        
    except Exception as e:
        print(f"Virhe luodessa luokkaa: {e}")
        return

def create_student():
    raw = input("Oppilastunnus (231054 / o231054): ").strip()
    uid = normalize_uid(raw)

    if not uid:
        print("Virhe: Tunnus väärin")
        return

    fname = input("Etunimi: ").strip()
    lname = input("Sukunimi: ").strip()

    if not fname or not lname:
        if not fname:
            print("Virhe: Etunimi puuttuu")
        else:
            print("Virhe: Sukunimi puuttuu")
        return

    try:
        api.Command.user_add(uid, givenname=fname, sn=lname,
            cn=f"{fname} {lname}", userpassword="changeme")
        print(f"Käyttäjä luotu: {uid} (salasana: changeme)")
        write_log(f"Luotiin käyttäjä {uid}")

    except errors.DuplicateEntry:
        print("Virhe: Käyttäjä on jo olemassa")
        return
    
    except Exception as e:
        print(f"Virhe käyttäjän luonnissa: {e}")
        return

    if input("Lisätäänkö luokkaan? (k/e): ").strip().lower() == "k":
        group = sanitize_class_name(input("Luokan nimi (esim. s23ätiv): ").strip())
        if not validate_class_name(group):
            print("Virhe: Luokan nimi väärässä muodossa")
            return
        try:
            api.Command.group_show(group)
            api.Command.group_add_member(group, user=[uid])
            print(f"Käyttäjä lisätty luokkaan {group}")
            write_log(f"{uid} lisätty luokkaan {group}")
        except errors.NotFound:
            print(f"Virhe: Luokkaa {group} ei ole")
            return
        except Exception as e:
            print(f"Virhe lisättäessä luokkaan: {e}")
            return

def add_students_to_class():
    raw = input("Oppilastunnukset pilkuilla tai välilyönneillä erotettuna: ")
    group = sanitize_class_name(input("Luokan nimi (esim. s23ätiv): ").strip())

    if not validate_class_name(group):
        print("Virhe: Väärä luokan muoto")
        return
    try:
        api.Command.group_show(group)
    except errors.NotFound:
        print(f"Virhe: Luokkaa {group} ei ole")
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

    normalized = list(dict.fromkeys(normalized))

    if not normalized:
        print(f"Virhe: {', '.join(skipped)}")
        return

    try:
        result = api.Command.group_add_member(group, user=normalized)

        completed_count = result.get("completed", 0)
        added = normalized[:completed_count]

        failed_section = result.get("failed", {})
        failed_users = []

        if isinstance(failed_section, dict):
            member = failed_section.get("member", {})
            if isinstance(member, dict):
                failed_users = member.get("user", [])

        for uid, reason in failed_users:
            skipped.append(f"{uid} ({reason})")

    except Exception as e:
        skipped.extend([f"{uid} (lisäys epäonnistui: {e})" for uid in normalized])
        added = []

    print("------------------------------------------------")
    print("Luokka:", group)

    if added:
        print(f"Lisätty: {', '.join(added)}")
        write_log(f"Lisätty luokkaan {group}: {', '.join(added)}")

    if skipped:
        print(f"Ohitetut: {', '.join(skipped)}")
        write_log(f"Ohitetut: {', '.join(skipped)}")

    print("------------------------------------------------")

def list_classes():
    result = api.Command.group_find(
        criteria="s",
        sizelimit=0
    )
   
    print("Luokat:")

    groups = sorted(
        g["cn"][0]
        for g in result["result"]
        if g.get("cn") and validate_class_name(g["cn"][0])
    )

    for g in groups:
        print(g)

def list_students():
    if input("Rajataanko luokan mukaan? (k/e): ").strip().lower() == "k":
        group = sanitize_class_name(
            input("Luokan nimi (esim. s23ätiv): ").strip()
        )

        if not validate_class_name(group):
            print("Virhe: Luokan nimi väärässä muodossa")
            return

        try:
            api.Command.group_show(group)

            result = api.Command.user_find(
                in_group=group,
                all=True,
                sizelimit=0
            )

            users = result["result"]

            if not users:
                print(f"Ryhmässä {group} ei löytynyt käyttäjiä")
                return

        except errors.NotFound:
            print(f"Virhe: Luokkaa {group} ei ole")
            return
        except Exception as e:
            print(f"Virhe käyttäjiä haettaessa: {e}")
            return


    else:
        users = api.Command.user_find(
            all=True,
            sizelimit=0
        )["result"]

    print("------------------------------------------------")
    print("{:<15} {:<20} {:<20}".format("Tunnus", "Etunimi", "Sukunimi"))
    print("------------------------------------------------")

    for u in users:
        uid = u["uid"][0]

        if not UID_RE.fullmatch(uid):
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

ipa_initialized = False

while True:
    if not ipa_initialized:
        init_ipa()
        ipa_initialized = True
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

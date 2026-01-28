#!/bin/bash
# Author: Arttumiro
# Description: Auttaa hallitsemaan IPA käyttäjiä ja käyttäjäryhmiä terminaalista.

# Tarkista Sudo
if [[ $EUID != 0 ]]; then
    echo "Suorita scripti Root oikeuksilla (sudo)"
    exit 1
fi

# Tarkista IPA-oikeudet
if ! ipa user-find --sizelimit=1 &>/dev/null; then
    echo "Kerberos-tiketti puuttuu, tai sinulla ei ole riittäviä oikeuksia IPA-komentoihin!"
    echo "Suorita 'sudo kinit admin'"
    exit 1
fi

# Korvaa ä/ö > a/o automaattisesti ryhmän nimestä
sanitize_group_name() {
    printf '%s' "$1" \
    | sed 's/[Ää]/a/g; s/[Öö]/o/g' \
    | tr '[:upper:]' '[:lower:]'
}
# Lisää "o" käyttäjänimen alkuun tarvittaessa
normalize_uid() {
    local uid="$1"
    uid=$(echo "$uid" | xargs)

    # Jos alkaa numerolla ja on 6 merkkiä → lisää 'o'
    if [[ "$uid" =~ ^[0-9]{6}$ ]]; then
        echo "o$uid"
        return 0
    fi

    # Jos oikeassa muodossa
    if [[ "$uid" =~ ^o[0-9]{6}$ ]]; then
        echo "$uid"
        return 0
    fi

    # Virheellinen
    return 1
}
validate_group_name() {
    local g="$1"
    if [[ "$g" =~ ^s[0-9]{2}[a-z]{4}$ ]]; then
        return 0
    fi
    return 1
}
# Luo uusi luokka ryhmä
create_group() {
    echo -n "Luokan nimike: "
    read -r class_raw

    # Tarkista että syöte ei ole tyhjä
    if [[ -z "$class_raw" ]]; then
        echo "Virhe: luokan nimeä ei annettu!"
        return
    fi

    class=$(sanitize_group_name "$class_raw")
    if ! validate_group_name "$class"; then
        echo "Virhe: ryhmän nimi '$class_raw' ei ole sallitussa muodossa!"
        echo "Sallittu muoto esim: s23ätiv. 's''kaksi numeroa''neljä kirjainta'"
        return
    fi
    if ipa group-show "$class" &>/dev/null; then
        echo "Virhe: Luokka '$class' on jo olemassa!"
    else
        ipa group-add "$class" --desc="Ryhmä luokalle $class" &>/dev/null
        echo "Luokka '$class' luotu (puhdistettu: $class_raw > $class)."
    fi
}

# Luo uusi oppilas käyttäjä, lisää "o" oppilastunnuksen eteen automaattisesti, sillä UNIX ei tue hyvin käyttäjänimiä, jotka alkaa numerolla
create_user() {
    echo -n "Anna oppilastunnus (esim 231054 tai o231054): "
    read -r username_raw

    # Tarkista että syöte ei ole tyhjä
    if [[ -z "$username_raw" ]]; then
        echo "Virhe: oppilastunnusta ei annettu!"
        return
    fi

    # Normalisoi uid (lisää o eteen jos puuttuu)
    username=$(normalize_uid "$username_raw") || {
    echo "Virhe: oppilastunnus väärin!"
    return
}
    if ipa user-show "$username" &>/dev/null; then
        echo "Virhe: Oppilas '$username' on jo olemassa!"
        return
    fi

    echo -n "Etunimi: "
    read -r fname
    if [[ -z "$fname" ]]; then
        echo "Virhe: etunimeä ei annettu!"
        return
    fi

    echo -n "Sukunimi: "
    read -r lname
    if [[ -z "$lname" ]]; then
        echo "Virhe: sukunimeä ei annettu!"
        return
    fi

    ipa user-add "$username" --first="$fname" --last="$lname" --password &>/dev/null <<EOF
changeme
changeme
EOF

    echo "Oppilas '$username' luotu. Salasana: 'changeme'"

    echo -n "Lisätäänkö oppilas luokkaan? (k/e): "
    read -r yn

    if [[ "$yn" == "k" ]]; then
        echo -n "Anna luokan nimi: "
        read -r group_raw

        group=$(sanitize_group_name "$group_raw")

        if ipa group-show "$group" &>/dev/null; then
            ipa group-add-member "$group" --users="$username" &>/dev/null
            echo "Käyttäjä lisätty ryhmään '$group' (puhdistettu: $group_raw > $group)."
        else
            echo "Virhe: Ryhmä '$group' ei ole olemassa!"
        fi
    fi
}

# Lisää oppilaita luokkaryhmään
add_user_to_group() {
    echo "Oppilastunnus alkaa aina 'o' kirjaimella, se lisätään automaattisesti, jos puuttuu "
    echo -n "Anna oppilastunnukset pilkuilla erotettuna (esim: o231054, 231111): "
    read -r usernames_raw

    usernames=$(echo "$usernames_raw" | tr ',' ' ')

    echo -n "Anna luokan nimi: "
    read -r group_raw

    group=$(sanitize_group_name "$group_raw")
    if ! validate_group_name "$group"; then
    	echo "Virhe: ryhmän nimi '$group_raw' ei ole sallitussa muodossa!"
    	return
    fi
    if ! ipa group-show "$group" &>/dev/null; then
        echo "Virhe: Luokka '$group' ei ole olemassa."
        return
    fi

    added=()
    skipped=()

    for user_raw in $usernames; do
        user=$(normalize_uid "$user_raw") || {
            skipped+=("$user_raw (virheellinen tunnus)")
            continue
	}
        if ipa user-show "$user" &>/dev/null; then
            if ipa group-add-member "$group" --users="$user" &>/dev/null; then
                added+=("$user")
            else
                skipped+=("$user (jo jäsen)")
            fi
        else
            skipped+=("$user (ei olemassa)")
        fi
    done

    echo "-----------------------------------------------------------"
    echo "Luokka: $group"
    [[ ${#added[@]} -gt 0 ]] && echo "Lisätty: ${added[*]}"
    [[ ${#skipped[@]} -gt 0 ]] && echo "Ohitetut: ${skipped[*]}"
    echo "-----------------------------------------------------------"
}

# Lista ryhmistä
list_groups() {
    echo "Luokat:"
    ipa group-find | grep -oE "\bs[0-9]{2}[a-zA-Z]+\b" | uniq
}

# Tulosta lista oppilaista
list_users() {
    echo -n "Haluatko rajata luokan mukaan? (k/e): "
    read -r yn

    group_filter=""
    members=""
    if [[ "$yn" == "k" ]]; then
        echo -n "Anna luokan nimi: "
        read -r group_raw
        group=$(sanitize_group_name "$group_raw")
	if ! validate_group_name "$group"; then
    	    echo "Virhe: ryhmän nimi '$group_raw' ei ole sallitussa muodossa!"
    	    return
	fi
        if ipa group-show "$group" &>/dev/null; then
            group_filter="$group"
            echo "Näytetään vain luokan '$group' oppilaat."
            members=$(ipa group-show "$group" --all --raw \
                | awk '/^  member: uid=/ {sub(/^  member: uid=/,""); sub(/,.*/,""); if ($0 ~ /^o[0-9]{6}$/) print $0}')
            if [[ -z "$members" ]]; then
                echo "-----------------------------------------------------------"
                echo "Luokassa '$group' ei ole yhtään oppilasta."
                echo "-----------------------------------------------------------"
                return
            fi
        else
            echo "Virhe: Luokka '$group' ei ole olemassa — näytetään kaikki oppilaat."
        fi
    fi

    echo "Oppilaat:"
    echo "-----------------------------------------------------------"
    printf "%-15s %-20s %-20s\n" "Tunnus" "Etunimi" "Sukunimi"
    echo "-----------------------------------------------------------"

    ipa user-find --all --raw | awk -v members="$members" '
        BEGIN {
            split(members, arr)
            for (i in arr) member[arr[i]]=1
        }
        /^  dn:/ {
            if (uid ~ /^o[0-9]{6}$/) {
                if (members=="" || (uid in member)) {
                    printf "%-15s %-20s %-20s\n", uid, fname, lname
                }
            }
            uid=fname=lname=""
        }
        /^  uid:/ {sub(/^  uid: /,""); uid=$0}
        /^  givenname:/ {sub(/^  givenname: /,""); fname=$0}
        /^  sn:/ {sub(/^  sn: /,""); lname=$0}
        END {
            if (uid ~ /^o[0-9]{6}$/) {
                if (members=="" || (uid in member)) {
                    printf "%-15s %-20s %-20s\n", uid, fname, lname
                }
            }
        }
    '

    echo "-----------------------------------------------------------"
}


# Menu
show_menu() {
    echo ""
    echo "============================="
    echo "   FreeIPA Luokkahallinta"
    echo "============================="
    echo "1) Uusi luokka"
    echo "2) Uusi oppilas"
    echo "3) Lisää oppilaita luokkaan"
    echo "4) Listaa kaikki luokat"
    echo "5) Listaa kaikki oppilaat"
    echo "6) Poistu"
    echo -n "Valitse vaihtoehto [1-6]: "
}

while true; do
    show_menu
    read -r choice
    case $choice in
        1) create_group ;;
        2) create_user ;;
        3) add_user_to_group ;;
        4) list_groups ;;
        5) list_users ;;
        6) echo "Valmis!"; exit 0 ;;
        *) echo "Ei tuettu vaihtoehto!" ;;
    esac
done

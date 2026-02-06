Oppilaiden hallinta kouluprojekti. Hyvin yksilöity tilanteeseen, ja en suosittelisi käyttöön. Julkisena tehtävänannon vaatimuksena.

Bash scripti suunniteltu toimimaan Linux pohjaisella FreeIPA palvelimella, käyttö esim SSH:n läpi. Testattu Fedora Server 42, 43. Johon asennettuna FreeIPA server, ja kieli asetettu olemaan Suomi.

Pitäisi toimia muissakin koneissa, kunhan vaatimukset täyttyy, ja käyttäjätunnuksien sekä ryhmien muoto on samaa.

Kehityksenä haluaisin lisätä .csv tiedostosta käyttäjien lisäämisen, tehdäkseen scriptistä paljon nopeamman ja helpomman käyttää muihin vaihtoehtoihin verrattuna (WebUI, käsin tiedon syöttäminen)

Sekä mahdollisesti myös muiden kielien kuten Python testaaminen, nopeuttakseen toimintaa, ilman että pitää käyttää ipa komentoa. (Python versio tehty)

Python scriptin vaatimukset: ipalib (tulee osana FreeIPA:a), python 3.10+, FreeIPA palvelimen jäsenyyden, tai suorituksen FreeIPA palvelimella.

Python scripti sisältää logaamisen, sekä paljon nopeamman toiminnan, hyödyntäen FreeIPA:n api:a, ipa komentojen sijasta.

Haluaisin lisätä viellä .csv syötön, mutta en tiedä CSV tiedoston avain/arvo pareja, josta saada oppilastunnus, etunimi, ja sukunimi.

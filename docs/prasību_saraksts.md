# Prasības – CRM mazai iestādei

## Funkcionālās prasības

| ID | Statuss | Prasība |
| --- | --- | --- |
| **F0** | ✅ done | Login un reģistrācija |
| **F1** |  | Organizācijas: izveidot, rediģēt, meklēt |
| **F2** |  | Kontaktpersonas pie organizācijas |
| **F3** |  | Mijiedarbību žurnāls |
| **F4** |  | Pieprasījumi no organizācijām |
| **F5** |  | Uzdevumi un atgādinājumi |
| **F6** |  | Meklēšana |
| **F7** |  | Pārskats vadītājam |
| **F8** |  | Piekļūstamības paziņojums |
| **F9** |  | [Kopsavilkuma ekrāns – vadības panelis](F9.md) |

## MI prasības

| ID | Statuss | Prasība | Prioritāte | MI akta riska klase |
| --- | --- | --- | --- | --- |
| **MI-1** |  | Mijiedarbības kopsavilkums un nākamā soļa ieteikums | MUST | Minimāls |
| **MI-2** |  | Organizāciju prioritizācija «pēc sadarbības potenciāla» | Lēmums «būvēt vai nē» | Klasificēt PIRMS izstrādes (iespējams augsts) |
| **MI-3** |  | E-pasta atbildes projekts | COULD | Minimāls |

**MI-1:** no brīva teksta → kopsavilkums + nākamais solis; marķēts «Ģenerēts ar MI»; darbinieks rediģē un apstiprina; saglabāts žurnālā.
**MI-2:** vērtē personas / organizācijas, tāpēc riska klasi nosaka pirms izstrādes; dokumentē, kas tiek vērtēts un kādas sekas organizācijai / personai.
**MI-3:** iekšējs teksts – MI sagatavo atbildes projektu, cilvēks to pārskata un nosūta pats; projekts marķēts «Ģenerēts ar MI».

## Nefunkcionālās prasības

| ID | Statuss | Prasība |
| --- | --- | --- |
| **N1** |  | Pieejamība |
| **N2** |  | Personas dati (VDAR) |
| **N3** |  | Lomas |
| **N4** |  | Tehnoloģijas un laiks |

## Lomu saraksts

| Loma | Apraksts | Redzamības apjoms |
| --- | --- | --- |
| **Nepieslēgts lietotājs** | Apmeklētājs, kas nav pieslēdzies sistēmai | Tikai pieslēgšanās, reģistrācijas un piekļūstamības paziņojuma lapa |
| **Darbinieks** | Atbild par savām organizācijām: kontakti, mijiedarbību žurnāls, uzdevumi | Tikai organizācijas, kurām viņš ir atbildīgais darbinieks, un ar tām saistītie dati |
| **Vadītājs** | Pārrauga komandas darbu | Visas organizācijas + pārskats |
| **Administrators** | Pārvalda lomas, datu dzēšanu un piekļuves žurnālu | Lietotāju konti, lomas, piekļuves žurnāls, dzēšanas pieprasījumi |

Loma tiek glabāta sesijā pēc pieslēgšanās.

### Lomu tiesības pa prasībām

| ID | Prasība | Nepieslēgts | Darbinieks | Vadītājs | Administrators |
| --- | --- | --- | --- | --- | --- |
| **F0** | Login un reģistrācija | Pieslēgties, reģistrēties | Izrakstīties | Izrakstīties | Izrakstīties |
| **F1** | Organizācijas | – | Izveidot, rediģēt, meklēt savas | Izveidot, rediģēt, meklēt visas; mainīt atbildīgo darbinieku | – |
| **F2** | Kontaktpersonas | – | Pārvaldīt savu organizāciju kontaktus | Pārvaldīt visus kontaktus | – |
| **F3** | Mijiedarbību žurnāls | – | Reģistrēt un skatīt savu organizāciju mijiedarbības | Skatīt visas mijiedarbības | – |
| **F4** | Pieprasījumi | – | Pārvaldīt savu organizāciju pieprasījumus | Skatīt un pārvaldīt visus pieprasījumus | – |
| **F5** | Uzdevumi un atgādinājumi | – | Savi uzdevumi | Savi uzdevumi; skatīt komandas uzdevumus | – |
| **F6** | Meklēšana | – | Meklēt savos datos | Meklēt visos datos | – |
| **F7** | Pārskats vadītājam | – | – | Pilna piekļuve | – |
| **F8** | Piekļūstamības paziņojums | Skatīt | Skatīt | Skatīt | Skatīt |
| **F9** | Vadības panelis | – | Personīgais kopsavilkums | Personīgais + komandas kopsavilkums | Administrēšanas kopsavilkums |
| **MI-1** | MI kopsavilkums un ieteikums | – | Ģenerēt, rediģēt, apstiprināt | Ģenerēt, rediģēt, apstiprināt | – |
| **MI-2** | MI prioritizācija | – | – | Tikai pēc lēmuma «būvēt» | – |
| **MI-3** | E-pasta atbildes projekts | – | Ģenerēt, rediģēt, nosūtīt pats | Ģenerēt, rediģēt, nosūtīt pats | – |
| **N2** | Datu dzēšana pēc pieprasījuma | – | – | – | Veikt dzēšanu |
| **N2** | Piekļuves žurnāls | – | – | – | Skatīt |
| **N3** | Lomu piešķiršana | – | – | – | Piešķirt un mainīt lomas |

## Konceptuālā arhitektūra

Lietotne «CRM» – FastAPI: JSON API pēc līguma `docs/openapi.yaml` un statiskas HTML lapas, kas ar JavaScript izsauc šo API (viens process, viens repozitorijs). API līgums ir patiesības avots; ja lietotne atbild citādi, tā ir kļūda lietotnē vai līgumā.

Palaišana: `uvicorn --factory app.main:create_app --reload`.

### Slāņi

| Slānis | Saturs |
| --- | --- |
| **Pārlūks** | HTML lapas ar JavaScript (`fetch`); formas un saraksti bez JavaScript nedarbojas. Darbojas ar tastatūru, ekrānlasītāju, 200 % mērogu un 320 px platumu |
| **Saskarne** | Statiskas lapas `app/static/*.html` ar kopīgu `style.css` un katrai lapai savu `*.js`. Paziņojumi pēc darbībām `role="status"`, lauku kļūdas pie laukiem, redzams fokuss. Pieslēgtā lietotāja lapām kopīga galvene `<header>` ar navigāciju `<nav>`, lietotāju un lomu tekstā un pogu "Izrakstīties" (`nav.js`, N3). *Skip-link un `<footer>` vēl nav (plānots ar F9)* |
| **API** | `app/main.py` maršruti pēc `docs/openapi.yaml`. Validācija atgriež vienotu `Error` shēmu ar lauku kļūdām; sesijas pārbaude pirms datu pārbaudes (bez sesijas vienmēr 401). Pieprasījumu kavējums tiek aprēķināts (ne glabāts) pēc šodienas Europe/Riga. Forma tiek nosūtīta ar `fetch`, lapa netiek pārlādēta (PRG netiek izmantots) |
| **Lapu maršruti** | `app/main.py` atdod HTML lapas; nepieslēgtu lietotāju novirza uz `/login` |
| **Drošība** | Paroles – `scrypt` jaucējvērtība (`app/security.py`); sesijas sīkdatne `session` (`HttpOnly`, `SameSite=Lax`), datu bāzē tikai marķiera jaucējvērtība. Loma katrā pieprasījumā tiek nolasīta no lietotāja konta caur sesiju; tiesības pārbauda serveris (N3). Pirmais administrators: `python -m app.cli set-role <e-pasts> ADMIN` |
| **Dati** | SQLite (`app/db.py`); fails no vides mainīgā `AUTH_DB_PATH`, noklusējums `auth.db` |
| **MI komponents** | *Plānots:* `app/ai.py` – MI-1, MI-2, MI-3 |
| **MI pakalpojums** | *Plānots:* GPAI API (Claude) vai atslēgvārdu imitācija ar vienādu funkcijas līgumu |
| **Testi** | `pytest` (`make test`) katram pieņemšanas kritērijam; līguma pārbaude `make lint-contract` |

### Ekrāni

| Grupa | Ekrāns | Maršruts | Prasības | Lomas | Stāvoklis |
| --- | --- | --- | --- | --- | --- |
| Visi | Pieslēgšanās / reģistrācija | `/login`, `/register` | F0 | Visi | Ir |
| Visi | Sākums / vadības panelis | `/panelis` | F9 | Pieslēgtie | Plānots |
| Visi | Piekļūstamības paziņojums | — | F8 | Visi | Plānots |
| Organizācijas | Saraksts un meklēšana | `/organizacijas` | F1, F6 | Darbinieks, vadītājs | Ir (F1) |
| Organizācijas | Organizācijas kartīte: pieprasījumi, žurnāls | `/organizacijas/{id}` | F1, F3, F4 | Darbinieks, vadītājs | Ir; kontakti plānoti (F2) |
| Organizācijas | Kontakta forma | — | F2 | Darbinieks, vadītājs | Plānots |
| Darbs | Mijiedarbība + MI-1 kopsavilkums | `/organizacijas/{id}` | F3, MI-1 | Darbinieks, vadītājs | Mijiedarbība ir; MI-1 plānots |
| Darbs | Pieprasījumi, statusi | `/pieprasijumi` | F4 | Darbinieks, vadītājs | Ir |
| Darbs | Mani uzdevumi | — | F5 | Darbinieks, vadītājs | Plānots |
| Vadība | Pārskats: tabula, diagramma | — | F7 | Vadītājs | Plānots |
| Administrēšana | Lomas, dzēšana, piekļuves žurnāls | `/admin` | N2, N3 | Administrators | Lomas ir (N3); dzēšana un piekļuves žurnāls plānoti (N2) |

### Datu modelis (SQLite)

| Tabula | Galvenie lauki | Stāvoklis |
| --- | --- | --- |
| `users` | e-pasts, paroles jaucējvērtība, vārds, loma | Ir (F0, N3) |
| `sessions` | marķiera jaucējvērtība, lietotājs | Ir (F0) |
| `organizations` | nosaukums, reģ. nr., adrese, atbildīgais darbinieks | Ir (F1); *plānots: veids* |
| `interactions` | organizācija, autors, veids, datums, kopsavilkums, nākamais solis | Ir (F3); *plānots: dalībnieki, MI marķējums* |
| `requests` | organizācija, nosaukums, apraksts, statuss, termiņš | Ir (F4) |
| `contacts` | vārds, amats, e-pasts, tālrunis, saziņas pamats, saziņas datums, glabāt līdz | Plānots (F2) |
| `tasks` | nosaukums, termiņš, izpildīts, saistītā organizācija / pieprasījums | Plānots (F5) |
| `access_log` | kas, ko, kad skatīja vai mainīja | Plānots (N2) |

### MI komponents (plānots, `app/ai.py`)

- Vienots funkcijas līgums: `kopsavilkums(teksts) → (kopsavilkums, nākamais_solis)`.
- Realizācija: GPAI API (Claude) vai atslēgvārdu imitācija; lietotnes loģika nav atkarīga no izvēlētās realizācijas.
- Visam MI ģenerētajam saturam: marķējums «Ģenerēts ar MI», cilvēks rediģē un apstiprina, saglabāts žurnālā.

### Caurviju prasības (visos slāņos)

| Joma | Prasības |
| --- | --- |
| **VDAR (N2)** | Datu minimizācija, glabāšanas termiņš, piekļuves žurnāls, dzēšana |
| **Pieejamība (N1)** | EN 301 549 / WCAG 2.2 AA, piekļūstamības paziņojums |
| **MI akts** | Riska klase pirms izstrādes, marķējums, cilvēks apstiprina |

## Atvērtie jautājumi

1. **N3 pret F0:** sākotnēji loma tika izvēlēta sākumlapā bez parolēm (mācību režīms), bet F0 ievieš pieslēgšanos. Jāprecizē N3 kritērijs.
2. **Ekrānu skaits:** arhitektūrā ir 9 ekrāni; ar F0 pieslēgšanos un administrēšanas ekrānu tie ir 11. Pieņemts, ka «Sākums / loma» kļūst par F9 vadības paneli.
3. **Administrators:** jānosaka, vai administrators apstiprina jaunas reģistrācijas (F0).

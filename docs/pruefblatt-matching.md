# Prüfblatt Matching – was bei den Dummy-Profilen herauskommen muss

Karte TASK-120.05 (Schritt 5), Stand 23.09.2026. Gegen dieses Blatt wird in
Schritt 8 (Matching-Dimensionen) und Schritt 9 (Beiträge → Merkmale) geprüft:
„Für die Dummy-Profile stimmt das Ranking mit dem Prüfblatt aus Schritt 5
überein; Abweichungen sind erklärt.“

Den Bestand legt `manage.py dummies_anlegen` an (siehe README, „Dummy-Bestand“);
die Werte jedes Dummys stehen wörtlich in `kern/dummies.py`. Die maschinenlesbare
Fassung dieses Blatts ist `docs/pruefblatt-matching.json`. Der Test
`kern/tests/test_dummies.py` prüft, dass beide dieselben Anker und Personen nennen,
dass jeder „nie“-Grund in den Daten tatsächlich vorliegt und dass kein
„muss“-Kandidat einen harten Filter reißt.

**So ist es zu lesen.** Je Anker-Profil ein kurzer Steckbrief, dann zwei Listen:

- **Muss unter die ersten fünf** – diese Kandidaten muss das Matching dem Anker
  unter seinen fünf besten Vorschlägen zeigen. Die Liste ist bewusst kurz (zwei,
  drei Namen); die übrigen Plätze sind frei.
- **Nie vorschlagen** – diese Kandidaten darf das Matching dem Anker nicht zeigen,
  mit dem Grund. Absichtlich stehen hier vor allem Leute, die *weich* gut passen
  würden: Ein harter Filter muss auch dann greifen, wenn alles andere stimmt.

Entfernungen sind Luftlinie zwischen den Ortsmitten (Haversine, `kern/geo.py`),
auf 0,1 km gerundet. Zwei Dummies im selben Ort stehen deshalb 0,0 km
auseinander.

## Lesarten – von Fabian bestätigt (23.09.2026)

Die Notiz sagt, *welche* Merkmale voreingestellt hart sind (Region + Radius,
Geschlechtspräferenz, Altersbereich-Wunsch, Verfügbarkeit), aber nicht, *wie*
genau sie filtern. Dieses Blatt legt es so fest. Die Zeilen entstanden als Annahmen der
Bausitzung; **Fabian hat sie am 23.09.2026 abends gelesen und bestätigt
(„passt so“, Karte TASK-120.05)** – sie gelten damit als seine Entscheidung:

1. **Beide Seiten zählen.** Ein Vorschlag ist nur zulässig, wenn er die harten
   Filter *beider* Personen einhält – nicht nur die des Ankers. Begründung: Der
   Kandidat bekommt den Anker seinerseits als Vorschlag gezeigt (Notiz: „beide
   nehmen unabhängig an“); ein Vorschlag, den die andere Seite nie bekommen dürfte,
   führt nie zu einer Verbindung.
2. **Radius:** Entfernung ≤ Radius des Ankers **und** ≤ Radius des Kandidaten.
   Gleichstand (genau auf der Grenze) zählt als drin. Luftlinie, nicht Fahrstrecke.
3. **Geschlechtspräferenz „gleich“:** Der andere muss dasselbe Geschlecht
   angegeben haben. „Keine Angabe“ ist nie „gleich“ – auch nicht zu jemand anderem
   mit „keine Angabe“ (Notiz: „wer nichts angibt, taucht in ‚nur Frauen‘-Suchen
   nicht auf“).
4. **Geschlechtspräferenz „gemischt“** filtert für einen *einzelnen* Vorschlag
   nichts – sie ist ein Wunsch an die Gruppe, nicht an die Person. Wirkt also wie
   „egal“. (Offen: ob „gemischt“ im Crew-Matching etwas bedeuten soll.)
5. **Alterswunsch:** Der Altersbereich des anderen muss zwischen „von“ und „bis“
   liegen (einschließlich). Leerer Wunsch = kein Filter. Hat der andere keinen
   Altersbereich angegeben, reißt er einen gesetzten Wunsch.
6. **Verfügbarkeit** bleibt in diesem Blatt **ohne Wirkung**: Kein Dummy hat eine
   *allgemeine* Verfügbarkeit (ohne Ausfahrtsbezug) eingetragen. Annahme: Wo keine
   Angabe da ist, filtert der harte Verfügbarkeitsfilter nicht. Wie er mit Angaben
   filtern soll (Überschneidung? wie viel?), ist offen – das braucht eine eigene
   Entscheidung, bevor Dummies allgemeine Verfügbarkeiten bekommen.
7. **No-Go** darf nie gerissen werden – Fabians allgemeine Regel aus Schritt 4:
   „das Matching soll niemanden vorschlagen, der ein No-Go reißt“. Das gilt für
   **jedes** No-Go, auch für reinen Freitext, und in **beide Richtungen**: Ein
   Muss-Kandidat darf kein No-Go des Ankers plausibel reißen, und der Anker keins
   des Kandidaten. Jeder Muss-Eintrag im JSON trägt dazu eine Begründung unter
   `nogo`. Im Prüfblatt gibt es deshalb zwei No-Go-Gründe:

   - **No-Go** (`nogo`, maschinell geprüft): die zwei Alkohol-No-Gos, für den Test
     auf das Feld „Alkohol auf Tour“ abgebildet:

     | wer | No-Go (Freitext) | reißt es bei „Alkohol auf Tour“ = |
     |---|---|---|
     | Nina | „keinen Tropfen, auch nicht abends in der Unterkunft, solange am nächsten Tag gefahren wird“ | „egal“ **und** „erst nach der Fahrt“ |
     | Petra | „Alkohol vor oder während der Fahrt“ | nur „egal“ |

     Bewusst ein Paar aus strenger und milder Fassung: Das Matching muss den
     Freitext *lesen*, ein Schlagwort „Alkohol“ genügt nicht.
   - **No-Go (Freitext)** (`nogo_freitext`, nicht maschinell geprüft): Der Kandidat
     besteht **alle** maschinell prüfbaren harten Filter, reißt aber nach
     verständiger Lesart ein Freitext-No-Go. Zwei Fälle: Sabine gegen Marcos
     „Heizen auf der Landstraße“ und Heinz gegen Uwes „Jeden Abend Hotel“. Das sind
     die eigentlichen Prüffälle für Schritt 8, weil das Urteil dort nur aus dem
     Freitext kommen kann. Der Test prüft bei ihnen nur, dass es die Person gibt
     und dass das No-Go-Feld des Ankers nicht leer ist.

   Wo ein No-Go nichts mit dem Kandidaten zu tun hat (Svens Autobahnetappen, Anjas
   Belehrungen, Franks Unpünktlichkeit, Gabis Rauchen …), steht das in der
   Begründung des Muss-Eintrags: „kein Hinweis“ heißt, im Profil und in den
   Beiträgen des anderen steht nichts, was es reißt.
8. **Ausschluss** (in irgendeiner Richtung) und **bestehende aktive Verbindung**
   (verbunden oder Ridebuddies) schließen einen Vorschlag immer aus.
9. **Crew-Mitgliedschaft ist kein Filter.** Ob das Matching Leute vorschlägt, die
   schon gemeinsam in einer Crew sind, ist nicht entschieden. Damit dieses Blatt
   nicht an der Frage hängt, sitzt **kein Anker mit einem seiner Muss- oder
   Nie-Kandidaten in derselben Crew**.
10. **hart/weich** steht bei allen Dummies auf der Voreinstellung; niemand hat ein
    Merkmal umgestellt.

### Grenzfälle am Radius

Bei diesen Paaren liegt die Luftlinie weniger als 1 km an der beidseitigen
Radiusgrenze (min. Radius beider). Keins davon steht als Muss oder Nie im Blatt;
ein Matching, das anders rundet oder mit Fahrstrecke rechnet, kippt sie aber. Nach
Lesart 2 (≤ gilt als drin) ist das Ergebnis:

| Paar | Luftlinie | Grenze | nach Lesart 2 |
|---|---|---|---|
| bonn-walter – frauen-yvonne | 30,84 km | 30 km | draußen |
| eifel-rainer – einsteiger-mia | 40,72 km | 40 km | draußen |
| eifel-rainer – frauen-melanie | 50,62 km | 50 km | draußen |
| eifel-rainer – schotter-mehmet | 50,12 km | 50 km | draußen |
| eifel-rainer – westerwald-gabi | 60,63 km | 60 km | draußen |
| einsteiger-luca – koeln-stefan | 40,3 km | 40 km | draußen |
| einsteiger-luca – ring-jens | 39,98 km | 40 km | drin |
| einsteiger-luca – ring-marco | 40,56 km | 40 km | draußen |
| frauen-melanie – westerwald-uwe | 49,87 km | 50 km | drin |
| koeln-markus – ring-jens | 60,17 km | 60 km | draußen |
| koeln-oliver – westerwald-uwe | 60,36 km | 60 km | draußen |
| koeln-stefan – westerwald-gabi | 60,08 km | 60 km | draußen |
| ohne-angabe-robin – westerwald-uwe | 49,61 km | 50 km | drin |
| ring-jens – schotter-jonas | 49,27 km | 50 km | drin |
| ring-jens – schotter-mehmet | 49,96 km | 50 km | drin |
| ring-marco – schotter-jonas | 50,25 km | 50 km | draußen |
| schotter-nina – westerwald-joerg | 49,49 km | 50 km | drin |

Die Liste steht auch im JSON unter `grenzfaelle`; der Test rechnet die Zahlen nach.

## Die Anker

### 1. dummy-schotter-sven – Enduro aus Siegburg

Enduro/Schotter und Landstraße, 35–44, Radius 40 km, zügig, Genießer, Zelt oder
Pension, kleine Gruppe. Themen: Tagestouren, Schrauben, Trainings. Alkohol erst
nach der Fahrt. No-Go: Autobahnetappen.

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-schotter-jonas | 3,6 km | beide Enduro, beide zügig, Halbtag und Tag, Zelt, kleine Gruppe; Tagestouren, Trainings, Schrauben gemeinsam |
| dummy-schotter-lea | 4,4 km | beide Enduro, beide zügig, beide Genießer mit Zelt/Pension in kleiner Gruppe; Tagestouren und Trainings gemeinsam |
| dummy-schotter-mehmet | 6,0 km | Enduro und Landstraße wie Sven, zügig, Halbtag/Tag um 250 km; Tagestouren und Schrauben gemeinsam. Sein „Alkohol egal“ reißt kein No-Go von Sven |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-schotter-tim | 4,1 km | Alterswunsch | Tim wünscht sich 18–24 bis 25–34, Sven ist 35–44 – der Filter der *Gegenseite* greift, obwohl Tim Enduro fährt und nebenan wohnt |
| dummy-schotter-nina | 10,9 km | No-Go | Ninas strenges Alkohol-No-Go gegen Svens „erst nach der Fahrt“ |
| dummy-eifel-rainer | 50,2 km | Radius | Adenau liegt außerhalb von Svens 40 km, obwohl Rainer Enduro fährt |

### 2. dummy-ring-marco – Rennstrecke vom Nürburgring

Sport/Rennstrecke und Landstraße, 35–44, Radius 80 km, sportlich,
Streckenfresser, Hotel. Themen: Trainings, Tagestouren. Kein Alkohol auf Tour.
No-Go: Heizen auf der Landstraße.

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-ring-kevin | 66,1 km | beide Sport/Rennstrecke, beide sportlich, Streckenfresser mit Hotel in kleiner Gruppe; Trainings gemeinsam. Marcos No-Go reißt er nicht: Profil nur Rennstrecke, im Beitrag „auf der Landstraße fahre ich nach Schild“ |
| dummy-ring-jens | 19,4 km | beide Sport/Rennstrecke, sportlich, Streckenfresser mit Hotel in kleiner Gruppe; Trainings gemeinsam; beide kein Alkohol. Profil nur Rennstrecke, kein No-Go |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-ring-sabine | 44,7 km | **No-Go (Freitext)** | Marcos „Heizen auf der Landstraße“: Sabine fährt Sport **und** Landstraße, sportlich, als Streckenfresserin – und kein Beitrag entschärft das. Alle maschinell prüfbaren Filter besteht sie; weich wäre sie Marcos beste Kandidatin. Hier muss das Matching den Freitext lesen |
| dummy-sauerland-kai | 145,8 km | Radius | Meschede, außerhalb beider Radien (je 80 km) – obwohl Kai auf die Rennstrecke will |
| dummy-fern-bernd | 415,6 km | Radius | München |

### 3. dummy-frauen-anja – Touring aus Bonn, nur mit Frauen

Landstraße und Touring, Frau, 35–44, Radius 50 km, **Präferenz „gleich“**,
**Alterswunsch 25–34 bis 45–54**. Zügig, Genießer, Pension oder Hotel. Themen:
Tagestouren, Fernreisen, Messen. Alkohol erst nach der Fahrt. No-Go:
ungefragte Belehrungen über ihre Fahrweise.

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-frauen-carla | 24,7 km | Frau mit „gleich“, 25–34 (im Wunsch); Landstraße und Touring, zügig, Genießer, Pension; Tagestouren und Messen gemeinsam |
| dummy-frauen-melanie | 9,9 km | Frau mit „gleich“, 45–54 (im Wunsch); Landstraße und Touring, zügig, Tag und Mehrtage, Pension/Hotel, kleine Gruppe; Tagestouren und Fernreisen gemeinsam |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-ohne-angabe-robin | 2,0 km | Geschlechtspräferenz | Robin gibt kein Geschlecht an und taucht deshalb in „nur Frauen“ nicht auf – obwohl Robin weich fast deckungsgleich mit Anja ist |
| dummy-frauen-petra | 8,6 km | Alterswunsch | Petra ist 55–64, Anjas Wunsch endet bei 45–54 |
| dummy-frauen-ines | 60,9 km | Radius | Montabaur, außerhalb von Anjas 50 km und Ines’ 40 km |
| dummy-schotter-nina | 21,4 km | No-Go | Ninas strenges Alkohol-No-Go gegen Anjas „erst nach der Fahrt“ – obwohl beide Touring, Fernreisen und Genießer sind |

### 4. dummy-schotter-nina – kein Alkohol, auch nicht abends

Enduro und Touring aus Neunkirchen-Seelscheid, Frau, 45–54, Radius 50 km,
Präferenz „gemischt“. Zügig, Genießer, Pension oder Hotel. Themen: Tagestouren,
Fernreisen. Kein Alkohol auf Tour. **No-Go: „Alkohol auf Tour – keinen Tropfen,
auch nicht abends in der Unterkunft, solange am nächsten Tag gefahren wird.“**

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-schotter-lea | 8,4 km | trinkt auf Tour nie; Enduro und Touring, zügig, Tag und Mehrtage, Genießerin; Tagestouren und Fernreisen gemeinsam |
| dummy-westerwald-gabi | 29,4 km | trinkt auf Tour nie; Touring, Mehrtage, Genießerin mit Pension; Fernreisen und Tagestouren gemeinsam |

**Nie vorschlagen** – drei Enduro-Fahrer aus der Nachbarschaft, alle am No-Go gescheitert:

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-schotter-mehmet | 10,0 km | No-Go | „Alkohol egal“, im Beitrag sogar das Bier zur Mittagspause |
| dummy-schotter-sven | 10,9 km | No-Go | „erst nach der Fahrt“, im Beitrag das Bier am Zelt |
| dummy-schotter-jonas | 14,2 km | No-Go | „erst nach der Fahrt“ |

### 5. dummy-westerwald-uwe – Reisender mit Zelt

Touring und Landstraße aus Hachenburg, 55–64, Radius 120 km, gemütlich,
Streckenfresser, Zelt oder Pension, Mehrtage bis 450 km. Themen: Fernreisen,
Tagestouren. Kein Alkohol auf Tour. No-Go: jeden Abend Hotel.

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-westerwald-gabi | 12,7 km | beide Touring, gemütlich, Mehrtage um 400–450 km, Zelt/Pension; Fernreisen und Tagestouren gemeinsam; beide kein Alkohol auf Tour. Sie zeltet – Uwes No-Go bleibt unberührt |
| dummy-westerwald-joerg | 9,2 km | Touring und Landstraße, gemütlich, Mehrtage um 400 km, Streckenfresser mit Zelt in kleiner Gruppe; Fernreisen und Tagestouren gemeinsam; beide kein Alkohol. Schläft nur im Zelt – Uwes No-Go bleibt unberührt |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-sauerland-heinz | 77,6 km | **No-Go (Freitext)** | Uwes „Jeden Abend Hotel – ich schlafe gern im Zelt“: Heinz übernachtet nur in Pension oder Hotel. Alle maschinell prüfbaren Filter besteht er, und weich passt er sehr gut (Touring, gemütlich, Fernreisen) – das Urteil muss aus dem Freitext kommen |
| dummy-siegen-klaus | 27,7 km | Ausschluss | Uwe hat die Verbindung mit „passt nicht“ beendet (Dimension Unterwegs). Weich wäre Klaus einer der Besten |
| dummy-schotter-lea | 47,0 km | Radius | für Uwes 120 km nah genug, aber Uwe liegt außerhalb von Leas 40 km – der Radius gilt beidseitig |
| dummy-frauen-ines | 24,7 km | Geschlechtspräferenz | Ines wünscht „gleich“, Uwe ist ein Mann – obwohl Touring, Mehrtage und Fernreisen passen |

### 6. dummy-einsteiger-luca – Anfänger, sucht Gleichaltrige

Landstraße aus Bonn-Bad Godesberg, 18–24, Radius 40 km, **Alterswunsch 18–24 bis
25–34**. Gemütlich, Halbtag um 120 km, Einsteiger. Themen: Feierabendrunden,
Trainings, Tagestouren. No-Go: Wheelies und Rasen in der Gruppe.

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-einsteiger-mia | 6,8 km | 18–24 (im Wunsch); Landstraße, gemütlich, Einsteigerin, Halbtag um 120 km; Feierabendrunden und Trainings gemeinsam |
| dummy-einsteiger-paul | 9,8 km | 25–34 (im Wunsch); Landstraße, gemütlich, Einsteiger; Feierabendrunden, Trainings und Tagestouren gemeinsam |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-bonn-walter | 6,8 km | Alterswunsch | 55–64 – obwohl gemütliche Feierabendrunden passen würden |
| dummy-frauen-carla | 31,3 km | Geschlechtspräferenz | Carla wünscht „gleich“, Luca ist ein Mann |
| dummy-schotter-sven | 13,4 km | Alterswunsch | 35–44 |

### 7. dummy-koeln-frank – mit Verbindungen und einem Ausschluss

Landstraße und Touring aus Köln, 45–54, Radius 60 km, zügig, Hotel oder
Pension, mittlere Gruppe. Themen: Tagestouren, Fernreisen, Messen. No-Go:
Unpünktlichkeit am Treffpunkt. Hat eine Verbindung (Dirk), einen Ridebuddy
(Stefan) und einen Ausschluss (Oliver).

**Muss unter die ersten fünf**

| Kandidat | Entfernung | warum |
|---|---|---|
| dummy-koeln-markus | 12,7 km | Landstraße und Touring, zügig, Tag und Mehrtage, „mal so, mal so“ mit Hotel/Pension in mittlerer Gruppe; Tagestouren, Fernreisen, Messen – alle drei gemeinsam |
| dummy-ohne-angabe-robin | 25,0 km | Frank hat „egal“ – ohne Geschlechtsangabe ist Robin für ihn kein Filterfall (Gegenstück zu Anja); Landstraße und Touring, zügig; alle drei Themen gemeinsam |

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-koeln-oliver | 13,2 km | Ausschluss | Frank hat Olivers Vorschlag (Runde 1) mit „passt nicht“ beantwortet, Dimension Tempo |
| dummy-koeln-dirk | 9,2 km | Verbindung | schon verbunden |
| dummy-koeln-stefan | 10,5 km | Verbindung | schon Ridebuddies |
| dummy-frauen-carla | 0,0 km | Geschlechtspräferenz | Carla wünscht „gleich“ – obwohl beide in Köln wohnen und Touring und Messen teilen |
| dummy-westerwald-uwe | 67,8 km | Radius | Hachenburg liegt knapp außerhalb von Franks 60 km |

### 8. dummy-fern-bernd – niemand in Reichweite

Sport und Touring aus München, 45–54, Radius 50 km. Der Störfall „außerhalb
jedes Radius“: Im Umkreis wohnt kein Dummy.

**Muss unter die ersten fünf:** niemand. Richtig ist eine **leere Liste** – das
Matching darf die Lücke nicht mit Fernen auffüllen.

**Nie vorschlagen**

| Kandidat | Entfernung | Grund | warum |
|---|---|---|---|
| dummy-ring-marco | 415,6 km | Radius | Nürburg – obwohl Sport/Rennstrecke passt |
| dummy-ring-kevin | 455,8 km | Radius | Köln |
| dummy-ring-sabine | 433,6 km | Radius | Bonn |

Ebenso ohne jeden Vorschlag bleibt **dummy-fern-hanna** (Hamburg, Radius 150 km).

## Beitragssignale für Schritt 9

Schritt 9 verlangt: „Ein Dummy-Beitrag verschiebt nachweislich ein Ranking.“
Diese Beiträge sind dafür angelegt (Text in `kern/dummies.py`, `BEITRAEGE`):

| Beitrag von | Stufe | Signal | erwartete Wirkung |
|---|---|---|---|
| dummy-einsteiger-paul | öffentlich | Profil sagt nur Landstraße – der Beitrag: Ténéré bestellt, Enduro-Grundkurs gebucht, „wer nimmt einen Anfänger mit ins Gelände?“ | Paul rückt für **Sven** und **Jonas** nach oben (vorher weich schwach: Landstraße, gemütlich). Er ist bewusst *nicht* auf Svens Muss-Liste, damit Schritt 8 ohne Beiträge besteht |
| dummy-schotter-mehmet | öffentlich | Bier oder Radler zur Mittagspause | bestätigt den No-Go-Konflikt mit Nina aus dem Freitext, nicht nur aus dem Feld |
| dummy-schotter-sven | öffentlich | „abends gern ein Bier am Zelt“ | dasselbe für Sven gegen Nina |
| dummy-ring-kevin | öffentlich | „auf der Landstraße fahre ich nach Schild“ | entschärft Marcos No-Go „Heizen auf der Landstraße“ – Kevin bleibt oben |
| dummy-ohne-angabe-robin | öffentlich | „mir geht es ums Fahren“ – kein Merkmal, aber ein Prüffall | **darf nicht wirken:** Robin hat keine Einwilligung zur KI-Auswertung (`Einwilligung` nur „18+“) |

Weitere Beiträge auf Stufe verbunden oder Ridebuddies (Anja, Yvonne, Nina, Gabi,
Heinz) tragen persönliche Angaben. Ob das Matching Beiträge jeder Stufe lesen
darf oder nur öffentliche, ist offen – die Notiz sagt „Rohmaterial fürs Matching
(mit Einwilligung)“, nicht welche Stufe.

## Terminfälle für Schritt 6

Schritt 6 rechnet je Termin einen Prozentwert aus dem Verfügbarkeitsraster,
Vorbehalte gewichtet. Wie stark ein Vorbehalt zählt, entscheidet Schritt 6; die
Fälle hier sind so gewählt, dass die Erwartung bei *jeder* Gewichtung klar ist.
S = sicher, V = mit Vorbehalt, N = nein.

**Nenner – offene Frage:** Zählen Gäste zur Crew? In jeder Crew ist einer Gast
(markiert mit G). Die Tabelle nennt beide Lesarten; bei der crewlosen Ausfahrt
sind die drei Teilnehmer der Nenner.

| Ausfahrt (Crew) | Termin | Antworten | mit Gast | ohne Gast | der Fall |
|---|---|---|---|---|---|
| Schotterrunde Bergisches Land (Schotterbande) | Sa 17.04.2027 vormittags | Jonas S, Mehmet S, Tim S, Rainer S, Lea(G) S | 5 S von 5 | 4 S von 4 | **100 %** |
| | So 18.04.2027 vormittags | Jonas S, Mehmet V, Tim S, Rainer V, Lea(G) S | 3 S, 2 V von 5 | 2 S, 2 V von 4 | **mit Vorbehalten** – wer mit Vorbehalt: Mehmet, Rainer |
| | Sa 24.04.2027 nachmittags | Jonas S, Mehmet N, Tim N, Rainer S, Lea(G) N | 2 S von 5 | 2 S von 4 | **mehrere fehlen** – Mehmet, Tim (und Lea) |
| Enduro-Grundlagentraining (Schotterbande) | Sa 08.05.2027 vormittags | Jonas S, Mehmet S, Tim V, Rainer N, Lea(G) S | 3 S, 1 V, 1 N | 2 S, 1 V, 1 N | **gleichauf** mit dem nächsten |
| | Sa 15.05.2027 vormittags | Jonas S, Mehmet N, Tim S, Rainer V, Lea(G) S | 3 S, 1 V, 1 N | 2 S, 1 V, 1 N | **gleichauf** – gleiche Zahlen, andere Leute |
| Frauenrunde Ahr und Eifel (Ladies on Tour) | So 02.05.2027 mittags | Carla S, Ayse S, Yvonne S, Petra(G) S | 4 S von 4 | 3 S von 3 | **100 %** |
| | So 09.05.2027 mittags | Carla S, Ayse S, Yvonne V, Petra(G) N | 2 S, 1 V, 1 N | 2 S, 1 V | |
| Messebesuch Frühjahrsmesse (Ladies on Tour) | Sa 10.04.2027 vormittags | Carla S, Ayse V, Yvonne V, Petra(G) S | 2 S, 2 V | 1 S, 2 V | |
| | So 11.04.2027 vormittags | Carla S, Ayse N, Yvonne S, Petra(G) N | 2 S, 2 N | 2 S, 1 N | |
| Renntraining Nürburgring (ohne Crew) | Sa 12.06.2027 vormittags | Kevin S, Sabine S, Marco V | 2 S, 1 V von 3 | – | Marco hat noch nicht zugesagt |
| | Sa 26.06.2027 vormittags | Kevin S, Sabine N, Marco S | 2 S, 1 N von 3 | – | |
| **Reise** Vogesen-Reise (Westerwald-Weitfahrer) | 03.–06.06.2027 | Gabi S, Heinz S, Ines S, Markus(G) V | 3 S, 1 V | 3 S von 3 | ohne Gast 100 % – hier entscheidet die Gast-Frage |
| | 17.–20.06.2027 | Gabi S, Heinz N, Ines S, Markus(G) N | 2 S, 2 N | 2 S, 1 N | |
| **Reise** Pfingsttour Harz (Westerwald-Weitfahrer) | 14.–17.05.2027 | Gabi S, Heinz S, Ines S, Markus(G) S | 4 S von 4 | 3 S von 3 | **100 %** |
| | 21.–24.05.2027 | Gabi V, Heinz S, Ines V, Markus(G) S | 2 S, 2 V | 1 S, 2 V | |

Die Reise-Antworten decken den Termin-Zeitraum jeweils genau ab
(`Verfuegbarkeitszeitraum` von–bis = `Termin` datum–bis_datum); Teilüberdeckungen
gibt es im Bestand nicht.

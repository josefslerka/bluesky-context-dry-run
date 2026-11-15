# Vstupy a měření

Všechny vstupy jsou místní UTF-8 JSON soubory vytvořené Codexem. `<run_dir>` vrací
`start`; `<skill-dir>` je adresář tohoto skillu. Shellové argumenty s mezerami cituj.

## Zdroj pro `source`

```json
{
  "url": "https://publisher.example/story",
  "title": "Název přečteného zdroje",
  "language": "cs",
  "text_kind": "excerpt",
  "paragraphs": ["Přesně zachycený odstavec z přečteného zdroje."],
  "published_at": "2026-11-12",
  "retrieved_via": "web tool",
  "caveats": ["Použit jen uvedený výřez, nikoli celý článek."]
}
```

`url` označuje skutečně čtený dokument. Připojovaný odkaz je původní URL ze `start`.
U Bluesky postu proto může být `url` adresa jeho odkazovaného článku. Volitelný
`post_uri` přidej jen podle skutečné veřejné API odpovědi, pomáhá odhalit citované
duplicity původního postu. `text_kind`: `full_text`, `excerpt`, `post_only`,
nebo `unavailable`. Poslední varianta má prázdné `paragraphs` a důvod v `caveats`.
`source.json` přidělí odstavcům ID `S001`, `S002` atd. Citace v hodnocení se musí
doslova nacházet v příslušném odstavci.

## Rešerše pro `collect`

```json
{
  "keywords": ["facial recognition", "biometric", "Corsight", "Luminova"],
  "web_queries": ["Skutečně provedené dotazy ve webovém vyhledávání"],
  "bsky_queries": ["facial recognition"],
  "actors": [
    {"handle": "eff.org", "provenance_url": "https://bsky.app/profile/eff.org"}
  ],
  "post_urls": []
}
```

Jde o ukázku formátu, ne pevný seznam témat či účtů. `keywords` jsou obsahové výrazy
pro předvýběr z feedů, nikoli tvrzení o sémantické vhodnosti. API vyhledávání nepoužívá
jazykový filtr. `post_urls` mohou obsahovat přímo nalezené veřejné posty i `at://` URI.
`candidates.json` přidělí stabilní ID podle URI a sloučí příspěvky stejného vlákna.

## Hodnocení pro `finalize`

```json
{
  "summary": "Stručný výsledek skutečně provedené rešerše.",
  "decisions": [
    {
      "candidate_id": "ID z candidates.json",
      "discussion_profile_id": "profile_id z discussion-profiles.json",
      "decision": "select",
      "relation": "comparative",
      "reason": "Proč článek dává v tomto konkrétním vlákně smysl.",
      "context_connection": "Na kterou část diskuse reakce navazuje.",
      "added_information": null,
      "language": "en",
      "draft_body": "Samostatná reakce pro toto vlákno, bez prefixu a bez URL.",
      "source_evidence": [{"paragraph_id": "S001", "quote": "Přesně zachycený odstavec"}],
      "context_evidence": [{"post_uri": "URI z contexts.json", "quote": "Přesný úryvek uloženého příspěvku"}],
      "limitations": ["Rozsah srovnání nebo jiné podstatné omezení."]
    }
  ],
  "limitations": ["Omezení pokrytí, dostupnosti zdroje a způsobu posouzení."]
}
```

Příklad obsahuje formátové popisy. Nahraď je skutečnými ID a doslovnými citacemi
z běhu, jinak validace neprojde. Před hodnocením vytvoř
[profily diskusí](discussion-profile.md). Nové běhy vyžadují odpovídající
`discussion_profile_id` u každého rozhodnutí s platným kontextem.
Pro `reject` jinak stačí `candidate_id`, `decision`
a `reason`; nepřidávej `draft_body`. Není povinné přidat rozhodnutí ke všem 30
automatickým kandidátům; přehled rozlišuje počet kandidátů a načtených kontextů.
Prázdné `decisions` jsou platné. Pět výsledků není povinná kvóta.

V nových bězích je hlavním filtrem tematická vhodnost doložená profilem diskuse.
`context_connection` popisuje konkrétní návaznost. `added_information` je volitelné:
může chybět nebo být `null`, například u podpory již vyslovené myšlenky.
Zdrojové a kontextové citace zůstávají povinné podle režimu; dokládají obsahovou
souvislost a tvrzení, nikoli povinnou novost informace.

Kandidát může být novou odpovědí ve starším vlákně. Kontextová čtečka ověří také
kořen vlákna. Chceš-li návrh adresovat původnímu příspěvku místo nalezenému komentáři,
přidej do rozhodnutí `reply_to_uri` s URI z ověřeného `contexts.json`. Přehled bude
odkazovat na tento skutečný cíl; nedovolí neověřené cílové URI.

Připojení zdroje provádí skript. Při dlouhé URL je v JSON kromě textu také `facets`
s UTF-8 indexy bohatého odkazu. To je místní datový návrh, ne pokyn k publikaci.

## Události pro `event`

Etapy modelové práce `model_stage` a odkaz na předchozí běh `revision_of` mají
formát a pravidla v [popisu workflow](workflow.md). Modelový záznam není lidskou
redakční kontrolou ani dokladem samostatného API volání.

```sh
python3 <skill-dir>/scripts/bluesky_dry_run.py event --run <run_dir> --input <event.json>
```

Požadavek na člověka: `{"kind":"human_request","reason":"Konkrétní chybějící údaj"}`.
Skript vrátí ID. Při odpovědi zapiš
`{"kind":"human_response","request_id":"vrácené ID","detail":"Co uživatel doplnil"}`.
Čekání se dopočítá automaticky; do aktivní lidské práce nevstupuje.

Nečekaná korekce: `{"kind":"human_correction","detail":"Skutečná změna od uživatele"}`.
Úvodní zadání tématu či URL ani interní rozhodnutí agenta sem nepatří.

Pokud uživatel čas skutečně změří, lze k lidské události doplnit
`"human_active_seconds":45,"time_basis":"user_reported"`; pro přímo měřenou
redakční kontrolu použij `time_basis=timed_editor_session` a `kind=human_review`.
Nevydávej dobu obsazení prohlížeče nebo čekání za aktivní práci člověka.

Dostupná dílčí spotřeba:

```json
{
  "kind": "usage",
  "provider": "skutečný poskytovatel",
  "measurement_source": "provider response / billing record",
  "input_tokens": 1000,
  "output_tokens": 200,
  "cached_input_tokens": 0,
  "cost_usd": 0.01
}
```

Čísla jsou příkladem formátu, nikoli cenou modelu nebo tohoto běhu. Pokud skutečné
usage nemáš, nevkládej tento příklad. Bez doloženého úplného účtování zůstane
`actual_cost_usd=null`; známé dílčí částky se vykážou samostatně. Výstup uvádí také
veřejné GET požadavky a jejich dobu. Tyto síťové časy nejsou dobou modelu ani jeho cenou.

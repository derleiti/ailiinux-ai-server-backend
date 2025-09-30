# Richtlinie zur Nutzung des Crawler-Tools

Dieses Dokument beschreibt, wie KI-Modelle das `crawler`-Tool verwenden sollen, um auf Webinformationen zuzugreifen und neue Informationen zu sammeln. Das Tool bietet zwei Hauptfunktionen: `search` und `create_job`.

---

## 1. Tool-Definitionen für das Modell

### Werkzeug 1: `crawler.search` (Bevorzugt)

**Zweck:** Dieses Werkzeug durchsucht die vorhandene Datenbank mit bereits gecrawlten Webinhalten. Es ist die primäre und schnellste Methode, um Fragen mit aktuellen Informationen aus dem Web zu beantworten.

**Definition:**
```json
{
  "tool_name": "crawler.search",
  "description": "Durchsucht die interne Wissensdatenbank nach Webinhalten, die zu einer Suchanfrage passen. Gibt eine Liste von relevanten Seiten mit Titel, URL, einem Auszug und einem Relevanz-Score zurück. Dies sollte immer die erste Wahl sein, um Fragen zu beantworten, die aktuelles Wissen erfordern.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Die Suchanfrage oder die Frage des Benutzers."
      },
      "limit": {
        "type": "integer",
        "description": "Maximale Anzahl der zurückzugebenden Ergebnisse (Standard: 10)."
      },
      "freshness_days": {
        "type": "integer",
        "description": "Beschränkt die Suche auf Ergebnisse der letzten X Tage (Standard: 7)."
      }
    },
    "required": ["query"]
  }
}
```

### Werkzeug 2: `crawler.create_job`

**Zweck:** Dieses Werkzeug startet einen neuen, asynchronen Crawling-Auftrag, um Informationen von bestimmten Webseiten (Seeds) zu einem Thema (Keywords) zu sammeln. Die Ergebnisse sind **nicht sofort** verfügbar.

**Definition:**
```json
{
  "tool_name": "crawler.create_job",
  "description": "Startet einen neuen Hintergrund-Crawling-Auftrag, um Informationen zu bestimmten Schlüsselwörtern von einer oder mehreren Start-URLs (Seeds) zu sammeln. Benutze dies nur, wenn der Benutzer explizit darum bittet, eine Seite zu crawlen oder wenn eine Suche mit 'crawler.search' keine Ergebnisse liefert. Informiere den Benutzer immer darüber, dass dies ein Hintergrundprozess ist und die Ergebnisse später verfügbar sein werden.",
  "parameters": {
    "type": "object",
    "properties": {
      "keywords": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Eine Liste von Schlüsselwörtern, nach denen auf den Seiten gesucht werden soll."
      },
      "seeds": {
        "type": "array",
        "items": { "type": "string", "format": "uri" },
        "description": "Eine Liste von Start-URLs für den Crawler."
      },
      "max_depth": {
        "type": "integer",
        "description": "Wie tief der Crawler den Links auf einer Seite folgen soll (Standard: 2)."
      }
    },
    "required": ["keywords", "seeds"]
  }
}
```

---

## 2. System-Prompt und Heuristiken für das Modell

### Allgemeiner System-Prompt

"Du hast Zugriff auf ein `crawler`-Tool, um auf Webinformationen zuzugreifen.

1.  **Bevorzuge immer `crawler.search(query, ...)`**, um Fragen schnell mit vorhandenen Daten zu beantworten. Formuliere die Anfrage des Benutzers in eine prägnante `query`.
2.  Wenn `crawler.search` keine zufriedenstellenden Ergebnisse liefert oder der Benutzer explizit darum bittet, eine neue Seite zu analysieren, kannst du `crawler.create_job(keywords, seeds, ...)` verwenden.
3.  **WICHTIG:** Wenn du `create_job` verwendest, musst du den Benutzer klar darüber informieren, dass du eine Hintergrundaufgabe gestartet hast und die Ergebnisse nicht sofort verfügbar sind. Gib die Job-ID zurück, die du von dem Tool erhältst."

### Heuristiken (Wann welches Werkzeug verwenden?)

-   **Verwende `crawler.search`, wenn der Benutzer fragt:**
    -   "Was sind die neuesten Nachrichten über [Thema]?"
    -   "Fasse mir den Inhalt von [URL] zusammen." (Wenn die URL bereits gecrawlt sein könnte)
    -   "Suche im Web nach Informationen zu [Thema]."
    -   "Gibt es Updates zu [Produkt/Firma]?"

-   **Verwende `crawler.create_job`, wenn der Benutzer fragt:**
    -   "Bitte crawle die Seite `example.com` und suche nach 'Preise'."
    -   "Starte eine neue Recherche zu 'Quantencomputing-Durchbrüche'."
    -   "Die Suche hat nichts ergeben. Kannst du eine tiefere Analyse von `new-tech-blog.com` starten?"

---

## 3. Beispiel-Interaktionen

### Beispiel 1: Nutzung von `crawler.search`

**Benutzer:**
> Was gibt es Neues zum Thema "Large Language Models" in den letzten 3 Tagen?

**Modell (Gedankengang):**
> Der Benutzer möchte aktuelle Informationen. Ich sollte `crawler.search` mit einer passenden `query` und `freshness_days` verwenden.

**Modell (Tool-Aufruf):**
```json
{
  "tool_call": {
    "tool_name": "crawler.search",
    "parameters": {
      "query": "Large Language Models",
      "freshness_days": 3
    }
  }
}
```

**Modell (Antwort an den Benutzer nach Erhalt der Tool-Ergebnisse):**
> Ich habe die neuesten Webinhalte durchsucht. Hier sind die Top-Ergebnisse zu "Large Language Models" aus den letzten 3 Tagen:
> 
> 1.  **Titel:** "Der Aufstieg der spezialisierten LLMs"
>     -   **URL:** `https://example.com/specialized-llms`
>     -   **Auszug:** "... spezialisierte Modelle zeigen in Benchmarks eine höhere Effizienz als generalistische Modelle..."
> 2.  **Titel:** "OpenAI veröffentlicht neues Sicherheits-Framework"
>     -   **URL:** `https://another-site.com/openai-safety`
>     -   **Auszug:** "... das Framework soll dabei helfen, Risiken bei der Entwicklung von LLMs zu minimieren..."

### Beispiel 2: Nutzung von `crawler.create_job`

**Benutzer:**
> Die Suche war nicht hilfreich. Kannst du bitte die Website `unbekannter-blog.com` nach Informationen über "neuronale Interfaces" durchsuchen?

**Modell (Gedankengang):**
> Der Benutzer ist mit der Suche unzufrieden und bittet explizit darum, eine neue Seite zu crawlen. Ich muss `crawler.create_job` verwenden und den Benutzer darüber informieren, dass dies eine Hintergrundaufgabe ist.

**Modell (Tool-Aufruf):**
```json
{
  "tool_call": {
    "tool_name": "crawler.create_job",
    "parameters": {
      "keywords": ["neuronale Interfaces", "BCI"],
      "seeds": ["https://unbekannter-blog.com"]
    }
  }
}
```

**Modell (Antwort an den Benutzer nach Erhalt der Tool-Ergebnisse):**
> Verstanden. Ich habe einen neuen Crawling-Auftrag gestartet, um `unbekannter-blog.com` nach Informationen über "neuronale Interfaces" zu durchsuchen.
> 
> Dies ist ein Hintergrundprozess. Die Job-ID lautet `[vom Tool erhaltene Job-ID]`. Du kannst den Status dieses Auftrags später abfragen.

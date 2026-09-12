#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Board Generator (Missionfrei / GoRemote)
--------------------------------------------------
Baut die index.html aus (1) automatischen Job-Feeds und (2) einer
manuellen Schicht (manual-jobs.json), die NIE automatisch geloescht wird.

- Live-Lauf (auf GitHub Actions):   python build_auto.py
- Lokaler Demo-Lauf (Cowork, kein Netz): python build_auto.py --mock

Design: uebernimmt template.html (das aktuelle Board) unveraendert und
ersetzt nur die 7 Bereichs-Sektionen. Login-Gate, Chips, Favoriten-Sterne,
Freelance, Toolbox, Footer bleiben wie sie sind.
"""
import json, re, sys, os, datetime, urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
MANUAL   = os.path.join(HERE, "manual-jobs.json")
OUT      = os.path.join(HERE, "index.html")
MOCK     = "--mock" in sys.argv
TODAY    = datetime.date.today().strftime("%d.%m.%Y")

# ---------- 7 Bereiche: Reihenfolge, Farbe, Label ----------
BEREICHE = [
    ("service",  "#0e7a52", "🟢 Service"),
    ("buero",    "#b07d10", "🟡 Büro & Orga"),
    ("start",    "#c2610c", "🟠 Schnell-Start"),
    ("sprache",  "#6d3fb0", "🟣 Sprache & Text"),
    ("marketing","#1e57b0", "🔵 Marketing & Kreativ"),
    ("vertrieb", "#b3261e", "🔴 Vertrieb & Sales"),
    ("it",       "#33333b", "⚫ IT & Tech"),
]

# ---------- Bereich-Zuordnung nach Stichwoertern (Titel/Tags) ----------
BEREICH_KW = {
    "service":  ["kundenservice","kundenbetreu","kundensupport","kundendienst","customer support","customer service","customer care","customer success","customer experience","customer advocate","support agent","support specialist","support consultant","support representative","support engineer","technical support","chat support","live chat","email support","help desk","helpdesk","service agent","client support","member support","player support","guest","reservation","booking","reise","travel","hospitality","concierge","call center","callcenter","kundenberat","beschwerde","content moderat","trust and safety","trust & safety","happiness engineer","community support","onboarding specialist","tier 1","tier 2","customer relations","client services","member services","user support","customer experience associate"],
    "buero":    ["buchhalt","accounting","accountant","finance","finanzbuch","lohn","payroll","steuerfach","controlling","sachbearbeit","büromanagement","bueromanagement","bürokaufmann","bürokauffrau","backoffice","back office","back-office","assistenz","assistant","virtual assistant","executive assistant","personal assistant","verwaltung","admin","office manager","operations specialist","operations coordinator","operations associate","customer operations","people operations","coordinator","scheduling","order management","datenerfassung","data entry","dateneingabe","bookkeep","procurement","recruit","talent acquisition","human resources","hr generalist","hr assistant","billing","claims","clerk","administrative","dispatcher","logistics coordinator","records management","personalsachbearbeit","office assistant","office administration","transcription"],
    "start":    [],   # frueher Mikrojobs - jetzt raus (Paul). Sektion zeigt nur noch manuelle Freelance-/Portal-Eintraege.
    "sprache":  ["übersetz","ubersetz","translat","lektor","proofread","texter","content writer","copywriter","redaktion","tutor","nachhilfe","language teacher","sprachlehrer"],
    "marketing":["marketing","social media","seo","content creator","content manager","grafik","design","designer","creative","video","brand","paid ads","performance market","kampagne","community manager"],
    "vertrieb": ["sales","vertrieb","sdr","sales development","setter","closer","business development","account executive","akquise","inside sales","account manager","partnerships","partner manager","bdr","revenue operations"],
    "it":       ["developer","engineer","software","devops","entwickl","programmier","backend","frontend","fullstack","full stack","data scientist","data analyst","qa engineer","it-support","it support","system admin","kotlin","python","javascript","react"],
}
BEREICH_ORDER = [b[0] for b in BEREICHE]

DE_MARKERS = ["deutsch","german","(m/w/d)","m/w/d","mwd","stelle","mitarbeiter","kundenbetreu","buchhalt","vertrieb","home office","homeoffice"]
# NUR starke "der Mensch darf ueberall sitzen"-Signale. RAUS: "global"/"weltweit" bar (=Firmen-Boilerplate
# "global agierendes Unternehmen"/"weltweit taetig" -> das ist KEIN weltweit-remote-Job). Paul-Fix: keine
# Deutschland-nur-Stellen mehr als "weltweit" faelschlich labeln.
WORLD_MARKERS = ["worldwide","anywhere","work from anywhere","work from any","location independent","location-independent","anywhere in the world","remote worldwide","fully remote worldwide","remote, global","fully distributed","from any country",
    "ortsunabhängig","ortsunabhaengig","von überall","von ueberall","standortunabhängig","standortunabhaengig","überall arbeiten","ueberall arbeiten","remote weltweit","weltweit remote","von zuhause aus überall"]
# Land-/Deutschland-gebunden: hat VORRANG vor World/EU (killt faelschliches "weltweit" aus Boilerplate).
# "deutschlandweit"/"bundesweit" = remote INNERHALB Deutschlands = Deutschland-nur.
DE_ONLY_MARKERS = ["deutschlandweit","bundesweit","nur in deutschland","innerhalb deutschlands","wohnsitz in deutschland","in deutschland ansässig","in deutschland ansaessig","must be based in germany","based in germany","germany-based","located in germany","residence in germany","germany only","remote (germany)","remote - germany","germany (remote)","remote in deutschland","deutschland (remote)"]
EU_MARKERS = ["europe","eu ","emea","cet","european","europaweit","eu-weit","euweit","innerhalb europas","remote in europa","eu remote","europe remote","remote europe","remote (europe)","eu-remote"]
EINSTEIGER_MARKERS = ["junior","entry","einsteiger","quereinstieg","quereinsteiger","no experience","keine erfahrung","berufseinsteiger","trainee","aushilfe","praktik"]
BLOCK = ["werkstud","working student",   # Paul: keine Werkstudenten
    # Paul: KEINE kleinen Nebenverdienst-/Mikrojobs (Umfragen, Klick-Tasks, Tests, KI-Datenlabeling, Transkription-Gigs)
    "umfrage","survey","paid survey","mikrojob","mikro-job","microtask","micro-task","clickwork","crowdwork","crowdsurf",
    "usability test","usability-test","website test","websites testen","produkttest","playtester","beta-test",
    "data annotation","datenannotation","annotator","data labeling","data labelling","daten labeln"," rater","quality rater","search evaluator","search engine evaluator","ads rating",
    "transcription","transkription","transkribent","untertitel erstellen",
    "ki-training","ki-daten","ki-sprachdaten","ki-trainer","ki-reviewer","ki-community","ai trainer","ai reviewer","audio evaluation","data evaluation",
    "get-paid","get paid to","paid to click","faucet","cashback","nebenverdienst","praemien sammeln","belohnungen verdienen"]

def esc(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").strip()

def clean_text(s, n=170):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n].rsplit(" ",1)[0] + ("…" if len(s) > n else "")

def detect_bereich(text):
    t = text.lower()
    for ber in BEREICH_ORDER:
        for kw in BEREICH_KW[ber]:
            if kw in t:
                return ber
    return None   # kein Match -> nicht aufnehmen (haelt das Board fokussiert)

def detect(job):
    """Ergaenzt lang/region/level anhand des Textes."""
    t = (job["title"] + " " + job.get("raw_loc","") + " " + job.get("raw_tags","") + " " + job.get("info","") + " " + job.get("raw_desc","")).lower()
    lang = "de" if any(m in t for m in DE_MARKERS) else "en"
    if any(m in t for m in DE_ONLY_MARKERS): region = "de"   # Land-gebunden hat Vorrang -> wird von der Weltweit-First-Regel gedroppt
    elif any(m in t for m in WORLD_MARKERS): region = "world"
    elif any(m in t for m in EU_MARKERS):  region = "eu"
    elif job.get("region_hint") in ("world","eu"): region = job["region_hint"]   # Feed-Hinweis (z.B. Adzuna: deutsch-remote = EU-Bruecke). DE_ONLY oben schlaegt ihn -> echt DE-gebundene fallen trotzdem raus.
    else: region = "de"   # ohne expliziten Weltweit-/EU-Marker: als Deutschland-nur behandeln (-> wird gefiltert)
    if job.get("no_world") and region == "world": region = "eu"   # Adzuna & Co (DE/EU-Markt): kein Fake-weltweit, hoechstens EU-Bruecke
    level = "einsteiger" if any(m in t for m in EINSTEIGER_MARKERS) else "erfahren"
    return lang, region, level

# ---------- Feeds ----------
def http_json(url):
    h={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"}
    if "rest.arbeitsagentur.de" in url: h["X-API-Key"]="jobboerse-jobsuche"   # oeffentlicher BA-App-Key (kein Signup)
    if "jsearch.p.rapidapi.com" in url:   # JSearch (RapidAPI): Key IM HEADER (nicht in der URL -> nicht geloggt)
        h["X-RapidAPI-Key"]=os.environ.get("JSEARCH_KEY","").strip()
        h["X-RapidAPI-Host"]="jsearch.p.rapidapi.com"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def from_arbeitnow(raw):
    out=[]
    for j in raw.get("data", []):
        if not j.get("remote"): continue   # arbeitnow ist gemischt - nur Remote-Jobs aufnehmen
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=" ".join(j.get("tags",[]) or [])+" "+" ".join(j.get("job_types",[]) or []),
            raw_desc=clean_text(j.get("description",""), 1000),
            raw_loc=j.get("location","") + " remote"))
    return out

def from_remotive(raw):
    out=[]
    for j in raw.get("jobs", []):
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=(j.get("category","")+" "+" ".join(j.get("tags",[]) or [])),
            raw_loc=j.get("candidate_required_location","")))
    return out

# Adzuna: Boersen-Aggregator, Deutschland-nativ (tappt dt. Boersen + Indeed-DE, die wir nicht scrapen).
# Nur Remote-Treffer aufnehmen (Adzuna ist gemischt). region_hint="eu" -> deutsch-remote als EU-Bruecke
# (echt DE-gebundene mit DE_ONLY-Marker fallen in detect() trotzdem raus). redirect_url hat numerische
# Ad-ID -> is_direct()=True. Braucht ADZUNA_APP_ID/KEY (GitHub-Secret); ohne Key wird die Quelle uebersprungen.
# Qualitaet (Paul: jede Stelle muss passen): nur ECHT voll-remote; Vor-Ort/Relocation/Hybrid raus.
ADZ_REMOTE = re.compile(r"100\s*%?\s*remote|fully remote|full[- ]?remote|voll(?:staendig|ständig)?\s*remote|komplett remote|remote[- ]?first|ortsunabh|standortunabh|work from anywhere|home\s?office|homeoffice|remote\s*\(?(?:eu|europe|europa)|eu[- ]?remote|remote in europa|von ueberall|von überall", re.I)
ADZ_ONSITE = re.compile(r"vor[- ]?ort|on[- ]?site|pr[äae]senz|relocat|umzug|umziehen|move to|nach (?:griechenland|zypern|portugal|spanien|bulgarien|malta|polen|rum[äa]nien|serbien|albanien|kroatien|t[üu]rkei)|ziehen nach|relocation package|based in (?:greece|cyprus|portugal|spain|bulgaria|poland)|hybrid|teilweise remote|tage (?:im )?b[üu]ro|b[üu]ro[- ]?pflicht", re.I)
def from_adzuna(raw):
    out=[]
    for j in (raw.get("results") or []):
        title=(j.get("title") or "").strip()
        desc=clean_text(j.get("description",""))
        loc=((j.get("location") or {}).get("display_name","")) or ""
        blob=title+" "+desc+" "+loc
        if not ADZ_REMOTE.search(blob): continue     # nur ECHT voll-remote
        if ADZ_ONSITE.search(blob):    continue     # Vor-Ort / Relocation / Hybrid raus (Qualitaet)
        out.append(dict(title=title, company=((j.get("company") or {}).get("display_name","")) or "",
            url=(j.get("redirect_url") or ""), info=desc,
            raw_tags=((j.get("category") or {}).get("label","")),
            raw_desc=clean_text(j.get("description",""),1000),
            raw_loc=loc+" remote", region_hint="eu", no_world=True))   # Adzuna = DE/EU-Markt: NIE als weltweit labeln
    return out

# Arbeitsagentur (Bundesagentur fuer Arbeit) - groesste Jobdatenbank DE, oeffentliche API, KEIN Key noetig.
# Paul-Wunsch: NUR echt weltweit machbare 100%-Remote-Stellen, immer Direktlink zur Stelle.
# Strategie: die Suche (SOURCES) ist bereits auf ortsunabhaengig/weltweit gebogen -> region_hint="world".
# detect() droppt trotzdem alles mit DE_ONLY-Marker (deutschlandweit/bundesweit/wohnsitz in DE).
# Direktlink = BA-Jobdetail-Seite zur konkreten Stelle (refnr) -> is_direct=True (Ziffern-ID).
def _ba_field(j, *names):
    for n in names:
        v=j.get(n)
        if isinstance(v,str) and v.strip(): return v.strip()
    return ""
def from_arbeitsagentur(raw):
    out=[]
    for j in (raw.get("stellenangebote") or []):
        title=_ba_field(j,"titel","beruf","stellenangebotsTitel","stellenbezeichnung")
        refnr=_ba_field(j,"refnr","referenznummer","hashId")
        if not title or not refnr: continue
        comp=_ba_field(j,"arbeitgeber","arbeitgeberName") or "Arbeitgeber (ueber Arbeitsagentur)"
        ao=j.get("arbeitsort") or {}
        ort=(ao.get("ort") if isinstance(ao,dict) else "") or _ba_field(j,"ort") or ""
        url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{urllib.parse.quote(refnr, safe='')}"
        out.append(dict(title=title, company=comp, url=url,
            info="Ortsunabhaengige Remote-Stelle (deutschsprachig, weltweit machbar) - Details und Bewerbung ueber den Link.",
            raw_tags=_ba_field(j,"beruf"), raw_loc=(ort+" ortsunabhaengig remote weltweit").strip(),
            raw_desc="", region_hint="world"))
    return out

def _j(x):  # list-oder-string -> string
    if isinstance(x,list): return " ".join(str(i) for i in x)
    return str(x or "")

def from_jobicy(raw):
    out=[]
    for j in raw.get("jobs", []):
        out.append(dict(title=j.get("jobTitle",""), company=j.get("companyName",""),
            url=j.get("url",""), info=clean_text(j.get("jobExcerpt","")),
            raw_tags=_j(j.get("jobIndustry"))+" "+_j(j.get("jobType")),
            raw_loc=_j(j.get("jobGeo"))))
    return out

def from_remoteok(raw):
    out=[]
    for j in (raw if isinstance(raw,list) else []):
        if not isinstance(j,dict) or not j.get("position"): continue
        out.append(dict(title=j.get("position",""), company=j.get("company",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=_j(j.get("tags")), raw_loc=(j.get("location") or "remote")))
    return out

# JSearch (RapidAPI / OpenWeb Ninja): aggregiert Google-for-Jobs (Indeed/LinkedIn/Glassdoor/ZipRecruiter)
# -> Quellen, die wir sonst nicht scrapen koennen. Braucht JSEARCH_KEY (GitHub-Secret, Header-Auth);
# ohne Key wird die Quelle uebersprungen. GLEICHES Quality-Gate wie Adzuna (Paul: jede Stelle muss passen):
# - remote_jobs_only=true in der Suche + job_is_remote/ADZ_REMOTE als Zusatz-Check
# - ADZ_ONSITE wirft Vor-Ort/Relocation/Hybrid raus (Google-for-Jobs ist rauschig, taggt Hybrid gern als remote)
# - job_apply_link = Direktlink zur Anzeige (is_direct() filtert Sammel-/Suchseiten in process() weiter)
# - region_hint="eu" + no_world=True: KEIN Fake-weltweit. deutsch-remote ist realistisch EU-gebunden ->
#   ehrlich als EU labeln (untertreiben ist ok, uebertreiben nicht). Echte Weltweit-Freigabe erst nach
#   Sichtung der realen Daten, nicht auf Verdacht.
def _jsearch_jobs(raw):
    """Findet die Job-Liste in der v2-Antwort, egal wie verschachtelt (data-Liste, data.jobs, top-level jobs...)."""
    if not isinstance(raw, dict): return []
    d = raw.get("data")
    lst = d if isinstance(d, list) else []
    if not lst and isinstance(d, dict):
        for k in ("jobs","results","items","data","docs"):
            if isinstance(d.get(k), list): lst = d[k]; break
    if not lst:
        for k in ("jobs","results","items"):
            if isinstance(raw.get(k), list): lst = raw[k]; break
    return [j for j in lst if isinstance(j, dict)]

# Weltweit-Erkennung (Paul: 100% remote WELTWEIT ist das Ziel). Ehrlich labeln:
# JS_WORLD = echte "von ueberall"-Signale -> region world. JS_LOCK = laendergebunden
# (US/UK only, "authorized to work in ...") -> raus, WENN nicht weltweit (nutzlos beim Auswandern).
JS_WORLD = re.compile(r"worldwide|work from anywhere|anywhere in the world|from anywhere|globally remote|global remote|remote\s*\(?global\)?|fully distributed|location[- ]independent|from any country|any location|no location restriction|work from any location|von ueberall|von überall|weltweit|ortsunabh|standortunabh", re.I)
JS_LOCK = re.compile(r"\b(us|u\.s\.?|usa|uk|canada|canadian|india|philippines)[- ]only\b|only\s+(?:open\s+)?(?:to|for)\s+(?:candidates|residents|applicants)?[^.]{0,30}\b(US|United States|UK|Canada|EU|EEA|Germany)\b|must (?:be|reside|live)[^.]{0,30}\b(US|United States|UK|Canada|Germany|Deutschland|EU|EEA)\b|based in (?:the )?(US|United States|UK|Canada)\b|authoriz(?:ed|ation) to work in|eligible to work in|work authorization in|(?:US|EU|UK|EEA)[- ]based only", re.I)

def from_jsearch(raw):
    out=[]
    jobs=_jsearch_jobs(raw)
    def g(j,*names):
        for n in names:
            v=j.get(n)
            if v is not None and v != "": return v
        return None
    for j in jobs:
        title=str(g(j,"job_title","title") or "").strip()
        if not title: continue
        full_desc=str(g(j,"job_description","description") or "")
        desc=clean_text(full_desc)
        city=str(g(j,"job_city","city") or ""); country=str(g(j,"job_country","country") or "")
        loc=" ".join(x for x in (city,country) if x)
        empl=str(g(j,"job_employment_type","employment_type") or "")
        blob=title+" "+clean_text(full_desc,2000)+" "+loc+" "+empl   # GANZE Beschreibung fuer Signal-Erkennung (world/lock/onsite), nicht nur 170 Zeichen
        if not (g(j,"job_is_remote","is_remote") or ADZ_REMOTE.search(blob)): continue   # muss echt remote sein
        if ADZ_ONSITE.search(blob): continue                                             # Vor-Ort/Relocation/Hybrid raus
        world = bool(JS_WORLD.search(blob))                                              # echt weltweit machbar?
        if not world and JS_LOCK.search(blob): continue                                  # laendergebunden + nicht weltweit -> raus (nutzlos beim Auswandern)
        link=str(g(j,"job_apply_link","apply_link","job_url","url") or "").strip()
        if not link:
            ao=j.get("apply_options") or j.get("job_apply_options")
            if isinstance(ao,list) and ao and isinstance(ao[0],dict):
                link=str(ao[0].get("apply_link") or ao[0].get("link") or "").strip()
        if not link: continue
        out.append(dict(title=title, company=str(g(j,"employer_name","company_name","company") or ""),
            url=link, info=desc,
            raw_tags=str(g(j,"job_publisher","publisher") or "")+" "+empl,
            raw_desc=clean_text(str(g(j,"job_description","description") or ""),1000),
            raw_loc=loc+(" weltweit remote" if world else " remote"), region_hint=("world" if world else "eu"), no_world=(not world)))  # weltweit NUR wenn die Anzeige es hergibt
    return out

def http_text(url):
    # Browser-UA + Accept: manche kuratierten Boards (z.B. RealWorkFromAnywhere) liefern Bot-UAs
    # eine HTML-/Challenge-Seite statt der RSS -> Parser bekam 0. Chrome-UA holt echte XML.
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
       "Accept":"application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
       "Accept-Language":"de,en;q=0.8"}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8","replace")

# ---------- Link-Check (laeuft auf GitHub mit offenem Netz) ----------
UA_LC={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}
def link_alive(url):
    """False NUR wenn der Link eindeutig tot ist (404/410). Alles andere (403/405/Timeout/DNS) -> behalten
    (Paul-Regel: nur sicher-tote Links entfernen)."""
    for method in ("HEAD","GET"):
        try:
            req=urllib.request.Request(url, method=method, headers=UA_LC)
            with urllib.request.urlopen(req, timeout=12) as r:
                return True
        except urllib.error.HTTPError as e:
            if e.code in (404,410): return False
            if method=="HEAD" and e.code in (403,405,501): continue  # HEAD verboten -> GET testen
            return True
        except Exception:
            return True   # Timeout/DNS/Verbindung -> im Zweifel behalten
    return True

def prune_dead(jobs, workers=24):
    if MOCK or not jobs: return jobs, 0
    import concurrent.futures as cf
    alive=[True]*len(jobs)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(link_alive, j["url"]): i for i,j in enumerate(jobs)}
        for f in cf.as_completed(futs):
            i=futs[f]
            try: alive[i]=f.result()
            except Exception: alive[i]=True
    kept=[j for j,a in zip(jobs,alive) if a]
    return kept, len(jobs)-len(kept)

def resolve_link(url):
    """Folgt Redirects -> (finale_url, lebt). lebt=False NUR bei 404/410 (Paul: nur sicher-tote raus).
    So werden Portal-/Redirect-Landing-URLs (Adzuna & Co) auf die ECHTE Einzelstelle beim Arbeitgeber
    aufgeloest -> Kandidat landet direkt auf der Anzeige, nicht auf einer Zwischenseite."""
    for method in ("HEAD","GET"):
        try:
            req=urllib.request.Request(url, method=method, headers=UA_LC)
            with urllib.request.urlopen(req, timeout=12) as r:
                return (r.geturl() or url), True
        except urllib.error.HTTPError as e:
            if e.code in (404,410): return url, False           # sicher tot -> raus
            if method=="HEAD" and e.code in (403,405,501): continue   # HEAD verboten -> GET testen
            try: return (e.geturl() or url), True               # anderer Fehler -> behalten
            except Exception: return url, True
        except Exception:
            return url, True   # Timeout/DNS/Verbindung -> im Zweifel behalten (Original-URL)
    return url, True

def resolve_and_prune(jobs, workers=32):
    """Board-weit: Redirect-/Portal-URLs auf die echte Einzelstelle aufloesen (nur wenn die aufgeloeste
    URL selbst direkt aussieht), sicher-tote Links (404/410) raus, danach nach URL re-deduplizieren."""
    if MOCK or not jobs: return jobs, 0, 0
    import concurrent.futures as cf
    res=[None]*len(jobs)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(resolve_link, j["url"]): i for i,j in enumerate(jobs)}
        for f in cf.as_completed(futs):
            i=futs[f]
            try: res[i]=f.result()
            except Exception: res[i]=(jobs[i]["url"], True)
    kept=[]; dead=0; resolved=0; seen=set()
    for j,(final,alive) in zip(jobs,res):
        if not alive: dead+=1; continue
        if final and final!=j["url"] and is_direct(final):
            j["url"]=final; resolved+=1
        u=j["url"].rstrip("/")
        if u in seen: continue          # nach Aufloesung koennen Dubletten entstehen -> raus
        seen.add(u); kept.append(j)
    return kept, dead, resolved

def from_rss_generic(xmltext):
    """RSS ohne 'Firma: Titel'-Konvention (euremotejobs, nodesk, realworkfromanywhere)."""
    import xml.etree.ElementTree as ET
    out=[]
    try: root=ET.fromstring(xmltext)
    except Exception: return out
    for item in root.iter("item"):
        title=(item.findtext("title") or "").strip()
        if not title: continue
        link=(item.findtext("link") or "").strip()
        desc=item.findtext("description") or ""
        comp=""
        for ch in item:
            if ch.tag.endswith("creator") and ch.text: comp=ch.text.strip(); break
        out.append(dict(title=title, company=comp, url=link, info=clean_text(desc),
            raw_tags=(item.findtext("category") or ""), raw_desc=clean_text(desc,1000), raw_loc=""))
    return out

def from_himalayas(raw):
    out=[]
    for j in raw.get("jobs", []):
        loc=_j(j.get("locationRestrictions"))
        out.append(dict(title=j.get("title",""), company=j.get("companyName",""),
            url=j.get("guid") or j.get("applicationLink") or "",
            info=clean_text(j.get("excerpt") or j.get("description","")),
            raw_tags=_j(j.get("categories")),
            raw_loc=loc if loc else "worldwide"))
    return out

def from_workingnomads(raw):
    out=[]
    for j in (raw if isinstance(raw,list) else []):
        if not isinstance(j,dict): continue
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=(j.get("category_name","")+" "+_j(j.get("tags"))),
            raw_loc=j.get("location","")))
    return out

# RemoteJobs.org (Lauf 31): freie JSON-API, worldwide-fokussiert. location-String z.B. "Remote (Worldwide)"
# -> detect() macht daraus world; "Remote (US)" o.ae. ohne Weltweit-Marker faellt als de raus. Gutes Non-Tech.

def from_wwr(xmltext):
    import xml.etree.ElementTree as ET
    out=[]
    try: root=ET.fromstring(xmltext)
    except Exception: return out
    for item in root.iter("item"):
        title=(item.findtext("title") or "").strip()
        region=(item.findtext("region") or "")
        comp,pos = (title.split(":",1)+[""])[:2] if ":" in title else ("",title)
        out.append(dict(title=(pos.strip() or title), company=comp.strip(),
            url=(item.findtext("link") or ""), info=clean_text(item.findtext("description") or ""),
            raw_tags=(item.findtext("category") or ""), raw_loc=region))
    return out

# ---------- ATS-Feeds: echte Einzelstellen direkt von Firmen-Bewerbungsboards ----------
# Greenhouse/Lever/Ashby haben offene JSON-APIs. Wir ziehen taeglich die AKTUELL
# offenen deutschsprachigen, breit-remote Rollen als ECHTE Einzelstellen-Links.
# Vorteil: laufen automatisch ab, wenn besetzt (naechster Build zieht sie nicht mehr),
# Link ist immer die konkrete Stelle (Badge "Direkt zur Stelle"), keine Handarbeit.
# Firma erweitern = eine Zeile. Slug muss stimmen (sonst 0/Fehler -> wird geloggt).
ATS_COMPANIES = [
    # (Anzeige-Firma, ats, slug, bereich-default, region-default)
    ("Bybit",      "greenhouse", "bybit",             "service", "world"),
    ("Bitpanda",   "greenhouse", "bitpanda",          "service", "eu"),
    ("OKX",        "greenhouse", "okx",               "service", "world"),
    ("Xapo Bank",  "greenhouse", "xapo61",            "buero",   "world"),
    ("Automattic", "greenhouse", "automatticcareers", "service", "world"),
    ("Remote.com", "greenhouse", "remotecom",         "service", "world"),
    ("Binance",    "lever",      "binance",           "service", "world"),
    ("Gate.io",    "lever",      "gate",              "service", "world"),
    ("Kraken",     "ashby",      "kraken.com",        "service", "world"),
    # --- Lauf #19: mehr Weltweit-Remote-Firmen (Slugs im Browser gegen die Board-API verifiziert) ---
    # Reise/Hospitality (fuer Lisa):
    ("Cloudbeds",  "greenhouse", "cloudbeds",         "service", "world"),
    ("Lodgify",    "lever",      "lodgify",           "service", "world"),
    ("Hopper",     "ashby",      "hopper",            "service", "world"),
    ("Going",      "ashby",      "going",             "service", "world"),
    # Kundenservice / Support / Remote-First (fuer Annette + Lisa-CS):
    ("Cloudflare", "greenhouse", "cloudflare",        "service", "world"),
    ("GitLab",     "greenhouse", "gitlab",            "service", "world"),
    ("Coinbase",   "greenhouse", "coinbase",          "service", "world"),
    ("Gemini",     "greenhouse", "gemini",            "service", "world"),
    ("Customer.io","greenhouse", "customerio",        "service", "world"),
    ("Aha!",       "greenhouse", "aha",               "service", "world"),
    ("Elastic",    "greenhouse", "elastic",           "service", "world"),
    ("Grafana Labs","greenhouse","grafanalabs",       "service", "world"),
    ("Vercel",     "greenhouse", "vercel",            "service", "world"),
    ("Webflow",    "greenhouse", "webflow",           "service", "world"),
    ("Linear",     "ashby",      "linear",            "service", "world"),
    ("Ramp",       "ashby",      "ramp",              "service", "world"),
    ("withClutch", "ashby",      "withclutch",        "service", "world"),
    # Lauf #22: Reisebranche/Hotel-Tech (fuer Lisa) - Slugs im Browser gegen die Board-API verifiziert.
    # region-default "eu" (NICHT world): reine "Remote"-Rollen dieser Firmen sind meist EU-remote,
    # nicht echt weltweit -> ehrlich als EU-Bruecke einsortieren, kein Fake-"weltweit".
    # Echt-weltweite Rollen (Location sagt worldwide/anywhere) werden trotzdem als world erkannt.
    ("Mews",         "greenhouse", "mewssystems",  "service", "eu"),
    ("apaleo",       "greenhouse", "apaleo",       "service", "eu"),
    ("GetYourGuide", "greenhouse", "getyourguide", "service", "eu"),
    ("trivago",      "greenhouse", "trivago",      "service", "eu"),
    ("Lighthouse",   "greenhouse", "lighthouse",   "service", "eu"),
    ("Revinate",     "lever",      "revinate",     "service", "eu"),
]
# Sprach-Signal. Trick: \bgerman\b trifft "German" (Sprache) aber NICHT "Germany" (Land) -
# so faellt "Country Manager, Germany" raus, "German Support/Speaker" bleibt drin.
# Titel darf breit sein; Description strenger (sonst triggert "expand into the German market").
ATS_GER_TITLE = re.compile(r"\bgerman\b|\bdeutsch\b|deutschsprachig|deutschkenntnisse", re.I)
ATS_GER_DESC  = re.compile(r"german[\s\-]?speak|deutschsprachig|fluent in german|native german|deutschkenntnisse|verhandlungssicher|proficiency in german|german language|business[\s\-]?level german", re.I)
ATS_REMOTE   = re.compile(r"\bremote\b|anywhere|worldwide|work from home|home[\- ]?office|distributed|\bwfh\b", re.I)
ATS_WORLD    = re.compile(r"worldwide|anywhere|\bglobal\b|work from anywhere|fully distributed|\bdistributed\b|any location|remote - global|from any country", re.I)
ATS_EU       = re.compile(r"\bemea\b|europe|european|\beu\b|\bcet\b|\bdach\b", re.I)
ATS_SENIOR   = re.compile(r"senior|lead|principal|staff|head of|director|\bvp\b|vice president|manager|chief|expert", re.I)
# Kundennahe Rollen (fuer WELTWEIT-Englisch: Lisa hat DE C2+EN, Annette kann Englisch) - passt zu Lisa/Annette
ATS_CUSTFACING = re.compile(r"support|customer|success|happiness|\bcare\b|\bservice\b|guest|reservation|concierge|assistant|operations|moderation|community|help ?desk|\bclient\b|onboarding|trust ?&? ?safety", re.I)

def _ats_region(loc, region_default):
    """world/eu aus der Location; None = konkreter Ort/Land -> laendergebunden -> raus (Paul: weltweit ist Pflicht)."""
    l=(loc or "").lower()
    if ATS_WORLD.search(l): return "world"
    if ATS_EU.search(l):    return "eu"
    stripped=re.sub(r"remote|anywhere|global|work from home|home[\- ]?office|distributed|wfh|[,\-/()\s]", "", l)
    if stripped=="": return region_default     # war nur 'remote'/leer -> Firmen-Default
    return None                                # konkreter Ort (Berlin, Budapest, 'Germany - Remote') -> raus

def _ats_emit(company, title, url, loc, desc, remote_flag, ber_default, region_default):
    title=(title or "").strip()
    if not title or not url: return None
    remote_ok = remote_flag or bool(ATS_REMOTE.search((title+" "+(loc or "")+" "+(desc or "")).lower()))
    if not remote_ok: return None
    region=_ats_region(loc, region_default)
    if region is None: return None                       # laendergebunden ("Germany - Remote", "Budapest") -> raus
    german = bool(ATS_GER_TITLE.search(title) or ATS_GER_DESC.search(desc or ""))
    custfacing = bool(ATS_CUSTFACING.search(title))
    # deutschsprachig: world ODER eu ok. Englisch: world ODER eu + kundennah (Lisa/Annette koennen Englisch;
    # eu-remote = Spanien/Portugal/Zypern, echte Auswander-Basen -> "nicht Deutschland-nur" erfuellt).
    # Laendergebunden (Nordamerika, LATAM, einzelne Laender) bleibt via _ats_region=None draussen.
    if german:
        pass
    elif region in ("world","eu") and custfacing:
        pass
    else:
        return None
    ber=detect_bereich(title) or ber_default
    if ber=="it" and custfacing: ber=ber_default        # "Happiness/Support Engineer" = Kundenservice, nicht IT
    level="erfahren" if ATS_SENIOR.search(title) else "einsteiger"
    lang="de" if german else "en"
    if german:
        info=clean_text(desc,170) or f"{company}: deutschsprachige Remote-Stelle - aktuell offen, Details ueber den Link."
    else:
        info=clean_text(desc,170) or f"{company}: weltweit-remote Stelle (Englisch) - aktuell offen, Details ueber den Link."
    return dict(title=title, company=company, url=url, info=info,
                lang=lang, region=region, level=level, bereich=ber,
                date=TODAY, fd=False, src="ats")

def from_greenhouse(slug):
    d=http_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    out=[]
    for j in d.get("jobs",[]):
        loc=(j.get("location") or {}).get("name","")
        out.append((j.get("title",""), j.get("absolute_url",""), loc, "", False))
    return out

def from_lever(slug):
    d=http_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out=[]
    for j in (d if isinstance(d,list) else []):
        cat=j.get("categories") or {}
        loc=(cat.get("location","") or _j(cat.get("allLocations")))
        wt=(j.get("workplaceType","") or "")
        out.append((j.get("text",""), (j.get("hostedUrl") or j.get("applyUrl","")),
                    loc+" "+wt, j.get("descriptionPlain",""), wt.lower()=="remote"))
    return out

def from_ashby(slug):
    d=http_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    out=[]
    for j in d.get("jobs",[]):
        loc=(j.get("location","") or _j(j.get("secondaryLocations")))
        out.append((j.get("title",""), (j.get("jobUrl") or j.get("applyUrl","")),
                    loc, j.get("descriptionPlain",""), bool(j.get("isRemote"))))
    return out

def gather_ats():
    if MOCK: return []
    fx={"greenhouse":from_greenhouse,"lever":from_lever,"ashby":from_ashby}
    out=[]
    for company,ats,slug,ber,region in ATS_COMPANIES:
        try:
            rows=fx[ats](slug)
            emitted=[]
            for title,url,loc,desc,rf in rows:
                e=_ats_emit(company,title,url,loc,desc,rf,ber,region)
                if e: emitted.append(e)
            emitted.sort(key=lambda x:(x["lang"]!="de", x["level"]!="einsteiger"))  # deutsch + einsteiger zuerst behalten
            emitted=emitted[:8]                                                       # Deckel pro Firma gegen Flut
            out+=emitted
            print(f"[ats] {company} ({ats}/{slug}): {len(rows)} -> {len(emitted)} passend (deutsch|weltweit-englisch kundennah)")
        except Exception as ex:
            print(f"[ats] {company} ({ats}/{slug}) FEHLER: {ex}")
    return out

# (name, url, normalizer, kind) - kind "json"|"text"
SOURCES = [
    # --- Deutschsprachig-orientiert (fuer die >=50%-Deutsch-Quote) ---
    ("arbeitnow",     "https://www.arbeitnow.com/api/job-board-api",         from_arbeitnow, "json"),
    ("arbeitnow-2",   "https://www.arbeitnow.com/api/job-board-api?page=2",  from_arbeitnow, "json"),
    ("arbeitnow-3",   "https://www.arbeitnow.com/api/job-board-api?page=3",  from_arbeitnow, "json"),
    ("arbeitnow-4",   "https://www.arbeitnow.com/api/job-board-api?page=4",  from_arbeitnow, "json"),
    ("arbeitnow-5",   "https://www.arbeitnow.com/api/job-board-api?page=5",  from_arbeitnow, "json"),
    ("remotive-de",   "https://remotive.com/api/remote-jobs?search=german",  from_remotive, "json"),
    ("remotive-de2",  "https://remotive.com/api/remote-jobs?search=deutsch", from_remotive, "json"),
    ("jobicy-de",     "https://jobicy.com/api/v2/remote-jobs?count=100&tag=german", from_jobicy, "json"),
    ("remoteok-de",   "https://remoteok.com/api?tags=german",         from_remoteok, "json"),
    # --- Weltweit (Volumen fuer die andere Haelfte) ---
    ("remotive",      "https://remotive.com/api/remote-jobs",         from_remotive, "json"),
    ("remotive-cs",   "https://remotive.com/api/remote-jobs?category=customer-support",   from_remotive, "json"),
    ("remotive-sales","https://remotive.com/api/remote-jobs?category=sales",              from_remotive, "json"),
    ("remotive-mkt",  "https://remotive.com/api/remote-jobs?category=marketing",          from_remotive, "json"),
    ("remotive-biz",  "https://remotive.com/api/remote-jobs?category=business",           from_remotive, "json"),
    ("remotive-data", "https://remotive.com/api/remote-jobs?category=data",               from_remotive, "json"),
    ("remotive-write","https://remotive.com/api/remote-jobs?category=writing",            from_remotive, "json"),
    ("remotive-fin",  "https://remotive.com/api/remote-jobs?category=finance-legal",      from_remotive, "json"),
    ("remotive-hr",   "https://remotive.com/api/remote-jobs?category=hr",                 from_remotive, "json"),
    ("remotive-pm",   "https://remotive.com/api/remote-jobs?category=project-management", from_remotive, "json"),
    ("remotive-all",  "https://remotive.com/api/remote-jobs?category=all-others",         from_remotive, "json"),
    ("jobicy",        "https://jobicy.com/api/v2/remote-jobs?count=100",             from_jobicy, "json"),
    ("jobicy-any",    "https://jobicy.com/api/v2/remote-jobs?count=100&geo=anywhere", from_jobicy, "json"),
    ("remoteok",      "https://remoteok.com/api",                     from_remoteok, "json"),
    ("himalayas",     "https://himalayas.app/jobs/api?limit=100",     from_himalayas, "json"),
    ("workingnomads", "https://www.workingnomads.com/api/exposed_jobs/", from_workingnomads, "json"),
    ("wwr",           "https://weworkremotely.com/remote-jobs.rss",   from_wwr, "text"),
    ("wwr-cs",        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",   from_wwr, "text"),
    ("wwr-salesmkt",  "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss", from_wwr, "text"),
    ("wwr-mgmtfin",   "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss", from_wwr, "text"),
    ("wwr-product",   "https://weworkremotely.com/categories/remote-product-jobs.rss",  from_wwr, "text"),
    ("wwr-allother",  "https://weworkremotely.com/categories/all-other-remote-jobs.rss", from_wwr, "text"),
    ("wwr-design",    "https://weworkremotely.com/categories/remote-design-jobs.rss",     from_wwr, "text"),
    # --- Weitere freie RSS-Boards ---
    ("euremotejobs",  "https://euremotejobs.com/feed/",                  from_rss_generic, "text"),
    # --- Runde: mehr Boersen + gezielte deutschsprachige/kundennahe Suchen ---
    ("remotive-kundenservice","https://remotive.com/api/remote-jobs?search=kundenservice",   from_remotive, "json"),
    ("remotive-support-de",   "https://remotive.com/api/remote-jobs?search=german%20support", from_remotive, "json"),
    ("remotive-reservation",  "https://remotive.com/api/remote-jobs?search=reservation",       from_remotive, "json"),
    ("remotive-travel",       "https://remotive.com/api/remote-jobs?search=travel",            from_remotive, "json"),
    ("remotive-assistant",    "https://remotive.com/api/remote-jobs?search=assistant%20german", from_remotive, "json"),
    ("jobicy-support",        "https://jobicy.com/api/v2/remote-jobs?count=100&industry=supporting", from_jobicy, "json"),
    ("jobicy-admin",          "https://jobicy.com/api/v2/remote-jobs?count=100&industry=admin",      from_jobicy, "json"),
    ("arbeitnow-6",           "https://www.arbeitnow.com/api/job-board-api?page=6", from_arbeitnow, "json"),
    ("arbeitnow-7",           "https://www.arbeitnow.com/api/job-board-api?page=7", from_arbeitnow, "json"),
    ("arbeitnow-8",           "https://www.arbeitnow.com/api/job-board-api?page=8", from_arbeitnow, "json"),
    ("remotewoman",           "https://remotewoman.com/feed/",                         from_rss_generic, "text"),
    ("jobicy-rss",            "https://jobicy.com/?feed=job_feed",                     from_rss_generic, "text"),
    # --- Lauf #19: neue Boards + gezielt Reise/Hospitality (Paul-Wunsch) ---
    ("remotive-hospitality",  "https://remotive.com/api/remote-jobs?search=hospitality", from_remotive, "json"),
    ("remotive-guest",        "https://remotive.com/api/remote-jobs?search=guest%20experience", from_remotive, "json"),
    ("remotive-booking",      "https://remotive.com/api/remote-jobs?search=booking",     from_remotive, "json"),
    ("remotive-concierge",    "https://remotive.com/api/remote-jobs?search=concierge",   from_remotive, "json"),
    ("jobicy-anywhere2",      "https://jobicy.com/api/v2/remote-jobs?count=100&geo=anywhere&industry=supporting", from_jobicy, "json"),
    ("cryptojobslist",        "https://cryptojobslist.com/feed",                        from_rss_generic, "text"),
    ("pangian",               "https://pangian.com/job-board/feed/",                     from_rss_generic, "text"),
    # --- Lauf #21: mehr kundennahe/deutsche Suchen (mehr Direkt-Einzelstellen) ---
    ("remotive-success",      "https://remotive.com/api/remote-jobs?search=customer%20success", from_remotive, "json"),
    ("remotive-va",           "https://remotive.com/api/remote-jobs?search=virtual%20assistant", from_remotive, "json"),
    ("remotive-moderator",    "https://remotive.com/api/remote-jobs?search=moderator",   from_remotive, "json"),
    ("remotive-onboarding",   "https://remotive.com/api/remote-jobs?search=onboarding",  from_remotive, "json"),
    ("remotive-german3",      "https://remotive.com/api/remote-jobs?search=deutschsprachig", from_remotive, "json"),
    ("jobicy-de2",            "https://jobicy.com/api/v2/remote-jobs?count=100&tag=deutsch", from_jobicy, "json"),
]

# --- Lauf #26: mehr freie Suchen (sofort, ohne Key) - profilnah (CS/Reise/Admin/deutsch) ---
SOURCES += [
    ("remotive-german-cust",  "https://remotive.com/api/remote-jobs?search=german%20customer", from_remotive, "json"),
    ("remotive-reise2",       "https://remotive.com/api/remote-jobs?search=reise",             from_remotive, "json"),
    ("remotive-hotel",        "https://remotive.com/api/remote-jobs?search=hotel",             from_remotive, "json"),
    ("remotive-billing",      "https://remotive.com/api/remote-jobs?search=billing",           from_remotive, "json"),
    ("remotive-community",    "https://remotive.com/api/remote-jobs?search=community",          from_remotive, "json"),
    ("remotive-account-mgr",  "https://remotive.com/api/remote-jobs?search=account%20manager",  from_remotive, "json"),
    ("jobicy-cust",           "https://jobicy.com/api/v2/remote-jobs?count=100&tag=customer-support", from_jobicy, "json"),
    ("jobicy-anywhere-admin", "https://jobicy.com/api/v2/remote-jobs?count=100&geo=anywhere&industry=admin", from_jobicy, "json"),
    ("remoteok-german",       "https://remoteok.com/api?tags=german",                          from_remoteok, "json"),
    ("arbeitnow-9",           "https://www.arbeitnow.com/api/job-board-api?page=9",             from_arbeitnow, "json"),
    ("arbeitnow-10",          "https://www.arbeitnow.com/api/job-board-api?page=10",            from_arbeitnow, "json"),
]

# --- Lauf #32: Volumen-Ausbau (Paul-Ziel 1000). Jobicy ist die ergiebigste freie API (100/Call)
#     -> alle relevanten Branchen x Regionen abgrasen. RemoteOK-Tags dazu. Dedup faengt Ueberschneidungen. ---
SOURCES += [
    # Jobicy nach Yield-Test: nur die Slugs die liefern (sales/finance = 400, geo=anywhere-Kombis = 429/0 -> raus, sonst kappt das Rate-Limit die guten Calls).
    ("jobicy-marketing",   "https://jobicy.com/api/v2/remote-jobs?count=100&industry=marketing",  from_jobicy, "json"),
    ("jobicy-business",    "https://jobicy.com/api/v2/remote-jobs?count=100&industry=business",    from_jobicy, "json"),
    ("jobicy-hr",          "https://jobicy.com/api/v2/remote-jobs?count=100&industry=hr",          from_jobicy, "json"),
    ("jobicy-management",  "https://jobicy.com/api/v2/remote-jobs?count=100&industry=management",  from_jobicy, "json"),
    ("jobicy-seller",      "https://jobicy.com/api/v2/remote-jobs?count=100&industry=seller",      from_jobicy, "json"),
    ("jobicy-copywriting", "https://jobicy.com/api/v2/remote-jobs?count=100&industry=copywriting", from_jobicy, "json"),
    ("jobicy-europe",      "https://jobicy.com/api/v2/remote-jobs?count=100&geo=europe",           from_jobicy, "json"),
    ("jobicy-emea",        "https://jobicy.com/api/v2/remote-jobs?count=100&geo=emea",             from_jobicy, "json"),
    ("remoteok-support2",  "https://remoteok.com/api?tags=customer+support", from_remoteok, "json"),
    ("remoteok-admin",     "https://remoteok.com/api?tags=admin",            from_remoteok, "json"),
    ("remoteok-nontech2",  "https://remoteok.com/api?tags=non+tech",         from_remoteok, "json"),
    ("remoteok-marketing", "https://remoteok.com/api?tags=marketing",        from_remoteok, "json"),
    ("remoteok-sales",     "https://remoteok.com/api?tags=sales",            from_remoteok, "json"),
]

# --- Arbeitsagentur (Lauf #27): groesste dt. Jobdatenbank, oeffentliche API, KEIN Key noetig.
#     Nur ortsunabhaengige/weltweit-machbare Treffer (Suche entsprechend gebogen). ---
def _ba(kw, size=100, page=1):
    return (f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
            f"?was={urllib.parse.quote(kw)}&size={size}&page={page}")
# GEPARKT (Paul: "danach vlt arbeitsagentur"): BA-API gab 0 zurueck (Auth hat sich geaendert,
# von hier aus nicht testbar) + Feeds bremsten den Build (Timeouts). Code bleibt, Quellen inaktiv.
# Zum Reaktivieren: den folgenden Block einkommentieren, sobald die Auth (OAuth-Token) steht.
# SOURCES += [
#     ("ba-ortsunabh-1",     _ba("ortsunabhängig",100,1),   from_arbeitsagentur, "json"),
#     ("ba-standortunabh",   _ba("standortunabhängig"),      from_arbeitsagentur, "json"),
#     ("ba-vonueberall",     _ba("von überall arbeiten"),    from_arbeitsagentur, "json"),
#     ("ba-anywhere",        _ba("work from anywhere"),      from_arbeitsagentur, "json"),
# ]
print("[ba] Arbeitsagentur geparkt (Auth offen) - inaktiv")

# --- Adzuna (Boersen-Aggregator, Deutschland-nativ). Nur aktiv, wenn ADZUNA_APP_ID/KEY als
#     GitHub-Secret gesetzt sind. Ohne Key: Quelle wird sauber uebersprungen (Board baut normal). ---
ADZUNA_ID  = os.environ.get("ADZUNA_APP_ID","").strip()
ADZUNA_KEY = os.environ.get("ADZUNA_APP_KEY","").strip()
def _adz(country, what, page=1):
    # max_days_old=40 -> nur frische Stellen (weniger abgelaufene "nicht verfuegbar"-Links).
    return (f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
            f"?app_id={ADZUNA_ID}&app_key={ADZUNA_KEY}&results_per_page=50&max_days_old=40"
            f"&what={urllib.parse.quote(what)}&content-type=application/json")
if ADZUNA_ID and ADZUNA_KEY:
    SOURCES += [
        # DE-Markt breit (deutschsprachig -> hebt Volumen UND die Deutsch-Quote). from_adzuna filtert hart auf ECHT voll-remote.
        ("adzuna-de-remote1",      _adz("de","remote"),                 from_adzuna, "json"),
        ("adzuna-de-remote2",      _adz("de","remote",2),               from_adzuna, "json"),
        ("adzuna-de-homeoffice",   _adz("de","homeoffice"),             from_adzuna, "json"),
        ("adzuna-de-homeoffice2",  _adz("de","homeoffice",2),           from_adzuna, "json"),
        ("adzuna-de-100remote",    _adz("de","100% remote"),            from_adzuna, "json"),
        ("adzuna-de-kundenservice",_adz("de","remote kundenservice"),   from_adzuna, "json"),
        ("adzuna-de-kundenbetr",   _adz("de","remote kundenbetreuung"), from_adzuna, "json"),
        ("adzuna-de-assistenz",    _adz("de","remote assistenz"),       from_adzuna, "json"),
        ("adzuna-de-sachbearb",    _adz("de","remote sachbearbeitung"), from_adzuna, "json"),
        ("adzuna-de-buchhaltung",  _adz("de","remote buchhaltung"),     from_adzuna, "json"),
        ("adzuna-de-marketing",    _adz("de","remote marketing"),       from_adzuna, "json"),
        ("adzuna-de-vertrieb",     _adz("de","remote vertrieb"),        from_adzuna, "json"),
        ("adzuna-de-reise",        _adz("de","remote reise"),           from_adzuna, "json"),
        # AT / CH - ebenfalls deutschsprachig
        ("adzuna-at-remote",       _adz("at","remote"),                 from_adzuna, "json"),
        ("adzuna-at-homeoffice",   _adz("at","homeoffice"),             from_adzuna, "json"),
        ("adzuna-ch-homeoffice",   _adz("ch","homeoffice"),             from_adzuna, "json"),
        ("adzuna-ch-remote",       _adz("ch","100% remote"),            from_adzuna, "json"),
        # Weitere EU-Maerkte (englisch, EU-remote)
        # GB / US (englisch, kundennah/Assistenz)
        # Seite 2 der ergiebigen Suchen + weitere EU-Maerkte (mehr Tiefe fuer die 1000)
        ("adzuna-de-kundenservice2",_adz("de","remote kundenservice",2),  from_adzuna, "json"),
        ("adzuna-de-assistenz2",   _adz("de","remote assistenz",2),       from_adzuna, "json"),
        ("adzuna-de-marketing2",   _adz("de","remote marketing",2),       from_adzuna, "json"),
        ("adzuna-de-buchhaltung2", _adz("de","remote buchhaltung",2),     from_adzuna, "json"),
        ("adzuna-de-vertrieb2",    _adz("de","remote vertrieb",2),        from_adzuna, "json"),
        ("adzuna-at-remote2",      _adz("at","remote",2),                 from_adzuna, "json"),
        # Kundenservice / aus-dem-Ausland gezielt (Paul-Wunsch: mehr wie das StudySmarter-Beispiel fuer Annette)
        ("adzuna-de-tech-cs",      _adz("de","technischer kundenservice remote"), from_adzuna, "json"),
        ("adzuna-de-kundenberater",_adz("de","kundenberater remote"),            from_adzuna, "json"),
        ("adzuna-de-cs-homeoffice",_adz("de","kundenservice homeoffice"),         from_adzuna, "json"),
        ("adzuna-de-ausland",      _adz("de","remote aus dem ausland"),           from_adzuna, "json"),
        # Seite 3 der ergiebigen Suchen -> ECHT neue (tiefere) Stellen, keine Dubletten (Volumen ehrlich Richtung 1000)
        ("adzuna-de-remote3",      _adz("de","remote",3),                 from_adzuna, "json"),
        ("adzuna-de-homeoffice3",  _adz("de","homeoffice",3),             from_adzuna, "json"),
        ("adzuna-at-remote3",      _adz("at","remote",3),                 from_adzuna, "json"),
        ("adzuna-ch-homeoffice3",  _adz("ch","homeoffice",3),             from_adzuna, "json"),
    ]
    print("[adzuna] Key gefunden -> Adzuna aktiv (51 Suchen, Tiefe + Kundenservice-Fokus)")
else:
    print("[adzuna] kein ADZUNA_APP_ID/KEY -> Adzuna uebersprungen (Key als GitHub-Secret setzen, dann aktiv)")

# --- JSearch (RapidAPI, Lauf #29): Google-for-Jobs (Indeed/LinkedIn/Glassdoor). Nur aktiv, wenn JSEARCH_KEY
#     als GitHub-Secret gesetzt ist. Header-Auth (Key NICHT in der URL). Gratis-Tier hat ein Monatslimit ->
#     bewusst schlank: 5 Anfragen/Build (num_pages=1), profilnah. Bei gutem Yield spaeter mehr Queries. ---
JSEARCH_KEY = os.environ.get("JSEARCH_KEY","").strip()
def _js(query, country="us", page=1):
    return (f"https://jsearch.p.rapidapi.com/search-v2"
            f"?query={urllib.parse.quote(query)}&page={page}&num_pages=1"
            f"&country={country}&remote_jobs_only=true&date_posted=month")
# Paul-Ziel: 100% remote WELTWEIT. Suchen bewusst auf "work from anywhere" gebogen (country=us =
# groesster Pool globaler Remote-Anzeigen); from_jsearch labelt world nur bei echtem Weltweit-Signal
# und wirft US-/laendergebundene raus. 1 de-Query fuer deutschen EU-Nachschub.
if JSEARCH_KEY:
    SOURCES += [
    ]
    print("[jsearch] deaktiviert: lieferte nur Portal-Links (glassdoor/indeed/jobrapido), die ins Leere laufen")
else:
    print("[jsearch] kein JSEARCH_KEY -> JSearch uebersprungen (Key als GitHub-Secret setzen, dann aktiv)")

def gather():
    jobs=[]
    if MOCK:
        for name in ("arbeitnow","remotive"):
            p=os.path.join(HERE,"mock",f"{name}.json")
            if os.path.exists(p):
                raw=json.load(open(p,encoding="utf-8"))
                fn={"arbeitnow":from_arbeitnow,"remotive":from_remotive}[name]
                jobs+=fn(raw); print(f"[mock] {name}: {len(fn(raw))}")
        return jobs
    for name,url,fn,kind in SOURCES:
        try:
            raw = http_text(url) if kind=="text" else http_json(url)
            got=fn(raw); jobs+=got
            print(f"[feed] {name}: {len(got)}")
        except Exception as e:
            print(f"[feed] {name} FEHLER (uebersprungen): {e}")
    return jobs

# ---------- Aufbereiten ----------
def process(raw_jobs):
    seen=set(); result=[]
    for j in raw_jobs:
        if not j.get("url") or not j.get("title"): continue
        blob=(j["title"]+" "+j.get("raw_tags","")+" "+j.get("info","")).lower()
        if any(b in blob for b in BLOCK): continue
        ber=detect_bereich(j["title"]+" "+j.get("raw_tags",""))
        if not ber: continue
        lang,region,level=detect(j)
        # WELTWEIT-FIRST (Paul): KEINE reinen Deutschland-Stellen. Aber ab Lauf #20 VOLLES Volumen:
        # ALLES weltweit ODER EU-remote behalten (deutsch UND englisch, alle Bereiche). Die Sortierung
        # (_rank: weltweit + deutsch + direkt ganz oben) und der CAP pro Bereich regeln Reihenfolge/Menge.
        if region not in ("world","eu"): continue        # nur Deutschland-nur/laendergebunden raus
        # Paul #21: aus den Job-Boards NUR Direkt-Links zur Einzelstelle aufnehmen (keine Karriere-/Firmenseiten).
        # Die Boards verlinken fast immer direkt auf die Anzeige -> genau die wollen wir.
        if not is_direct(j["url"]): continue
        u=j["url"].rstrip("/")
        if u in seen: continue
        seen.add(u)
        result.append(dict(title=j["title"], company=j.get("company",""),
            url=j["url"], info=j.get("info","") or "Remote-Stelle - Details ueber den Link.",
            lang=lang, region=region, level=level, bereich=ber, date=TODAY, fd=False, src="auto"))
    return result

def load_manual():
    if not os.path.exists(MANUAL): return []
    try: data=json.load(open(MANUAL,encoding="utf-8"))
    except Exception as e: print("manual-jobs.json Fehler:",e); return []
    out=[]
    for j in data:
        fd=bool(j.get("fd", True))
        out.append(dict(title=j["title"], company=j.get("company",""), url=j["url"],
            info=j.get("info",""), lang=j.get("lang","de"), region=j.get("region","de"),
            level=j.get("level","einsteiger"), bereich=j.get("bereich","service"),
            date=j.get("date",TODAY), fd=fd, src=j.get("src") or ("customer" if fd else "import")))
    return out

# ---------- Render ----------
def region_tag(r): return {"world":'<span class="tag world">🌍 Weltweit</span>',
    "eu":'<span class="tag eu">🇪🇺 EU</span>',"de":'<span class="tag de">🇩🇪 DE</span>'}.get(r,'')
def level_tag(l): return '<span class="tag lvl">🌱 Einsteiger</span>' if l=="einsteiger" else '<span class="tag">📈 Mit Erfahrung</span>'
def lang_tag(l):  return '<span class="tag delang">Deutsch</span>' if l=="de" else '<span class="tag">Englisch</span>'
def fd_tag(fd):   return '<span class="tag" style="background:#f3ead4;color:#a8842e;font-weight:650">⭐ Für dich</span>' if fd else ''

def is_direct(url):
    """True = Link fuehrt direkt zur Einzelstelle. False = Firmen-/Boersen-/Kategorie-/Suchseite (Liste).
    Reihenfolge wichtig: erst Suchseiten raus, dann STARKE Einzelstellen-Signale (Job-ID/UUID),
    dann Kategorie-/Sammel-Seiten raus, dann schwaechere Einzelstellen-Signale."""
    s=(url or "").lower().rstrip("/")
    path=re.sub(r"^https?://[^/]+","",s)
    if path=="": return False
    seg=path.split("?")[0].rstrip("/")
    last=seg.rsplit("/",1)[-1]
    # 0) Suchergebnis-/Filter-Seiten (Query-Parameter) -> nie eine Einzelstelle
    if re.search(r"[?&](search|q|query|keywords?|kw|geo|location|category|page)=", s): return False
    # 1) STARKE Einzelstellen-Signale zuerst: numerische Job-ID / UUID -> echte Stelle
    #    (auch bei /kategorie/slug-ID-Struktur wie remotive/arbeitnow/jobicy)
    if re.search(r"\d{5,}", path): return True
    if re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}", path): return True
    # 2) Sammel-/Kategorie-Slugs ohne ID (enden auf -jobs/-stellen/-companies ...) -> Boerse/Liste raus
    if re.search(r"-(jobs|stellen|companies|firms|firmen|joblist|jobsuche|listings?|roles|openings)$", last): return False
    # 3) Taxonomie-Pfade /remote-jobs|jobs/<kategorie-oder-land>/<...> ohne ID -> Kategorieseite raus
    if re.search(r"^/(remote-jobs|jobs|job-board|stellenmarkt|stellen)/[a-z][a-z-]{1,}/[a-z]", seg): return False
    # 4) bekannte Boersen-/Suchpfade
    if re.search(r"/(jobs-with|search-jobs|job-search|find-jobs|browse|explore|jobs-kundenservice|jobs-in|hotel-tech-companies)(/|-|$)", seg): return False
    # 5) generische Landing-/Karriereseiten -> keine Einzelstelle
    if re.search(r"/(careers?|jobs|hire|karriere|career|job-vacancies|vacancies|stellenangebote|stellen|join|openings|positions|offene-stellen|all-jobs)$", path): return False
    if re.search(r"/jobs?/(setter|closer|remote|homeoffice|appointment-setter|closer-deutschland|high-ticket)(/|$)", path): return False
    if "?title=" in s or s.endswith("/jobs") or s.endswith("/career"): return False
    # 6) schwaechere Einzelstellen-Signale
    if re.search(r"/(jobs?|job|o|position|stelle|vacancies|remote-jobs|remote/jobs|listing)/[a-z0-9][a-z0-9-]{6,}", path): return True
    if re.search(r"/companies/[^/]+/[a-z0-9]", path): return True
    if re.search(r"/[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+", path): return True # langer Slug (>=4 Woerter)
    return False

def card(j):
    d = is_direct(j["url"])
    badge = ('<span class="tag direct">→ Direkt zur Stelle</span>' if d
             else '<span class="tag firma">🏢 Firma · offene Stellen</span>')
    golabel = "Zur Stelle →" if d else "Zu den offenen Stellen →"
    return (f'<div class="card" data-bereich="{j["bereich"]}" data-level="{j["level"]}" data-lang="{j["lang"]}" data-direct="{1 if d else 0}">\n'
            f'  <h3>{esc(j["title"])}</h3>\n  <div class="company">{esc(j["company"])}</div>\n'
            f'  <p class="info">{esc(j["info"])}</p>\n'
            f'  <div class="meta">{region_tag(j["region"])}{level_tag(j["level"])}{lang_tag(j["lang"])}{fd_tag(j["fd"])}'
            f'{badge}<span class="tag date">📅 {j["date"]}</span></div>\n'
            f'  <div class="go"><a href="{j["url"]}" target="_blank" rel="noopener">{golabel}</a></div>\n</div>')

# Deckel pro Bereich - kippt den Mix Richtung Service/Buero statt IT-Flut.
# Lauf #20 (Paul: mehr Volumen) deutlich angehoben.
CAP={"service":600,"buero":400,"start":200,"sprache":200,"marketing":300,"vertrieb":250,"it":320}
def _rank(j):
    # Paul #21: (1) Deutschland-nur ganz unten, (2) DIREKT vor Firma (Firma fast raus -> unten),
    # (3) deutsch vor englisch (so weit oben wie moeglich), (4) weltweit vor EU, (5) ⭐ zuerst.
    # -> ganz oben in jeder Sektion: deutsch + direkt + weltweit.
    reg = j.get("region"); de = j.get("lang")=="de"; direct = is_direct(j.get("url",""))
    return (
        1 if reg=="de" else 0,        # Deutschland-nur (nicht weltweit) ganz unten
        0 if direct else 1,           # DIREKT zur Stelle zuerst, Firmen-/Karriereseiten nach unten
        0 if de else 1,               # deutsch vor englisch
        0 if reg=="world" else 1,     # weltweit vor EU
        0 if j.get("fd") else 1,      # ⭐ Fuer-dich zuerst
    )

# ==================== Personalisierte "Fuer dich"-Ansicht (Lauf #23) ====================
# Pro Login-Passwort eine gerankte Top-Auswahl aus DEMSELBEN Board. Nur Job-Kriterien
# pro Passwort (KEINE Namen/PII). Scoring laeuft im Browser (liest Titel/Info/Bereich/
# Sprache + Region-Badge der Karten). Alles in die Shell injiziert -> nur build_auto.py
# muss deployt werden, template.html bleibt unangetastet.

FD_CHIP = '<span class="chip" data-f="fd">⭐ Für dich</span>\n    '

# #fuerdich/#favoriten liegen ausserhalb .wrap (direkt an body) -> sonst volle Breite (5+ pro Reihe).
# Auf die Board-Breite (1120px, wie die normalen Sektionen) zentrieren -> 3 pro Reihe Desktop,
# 1 pro Reihe Handy (erbt die mobile .grid-Regel). Desktop+Handy konsistent mit dem restlichen Board.
FD_CSS = ('<style>#fuerdich,#favoriten{max-width:1120px;margin-left:auto;margin-right:auto;'
          'padding-left:22px;padding-right:22px;box-sizing:border-box}'
          '#fuerdich .grid,#favoriten .grid{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}'
          '@media(max-width:640px){#fuerdich,#favoriten{padding-left:14px;padding-right:14px}'
          '#fuerdich .grid,#favoriten .grid{grid-template-columns:1fr}}</style>\n')

FD_SECTION = ('<section id="fuerdich" class="hidden">\n'
  '  <h2 style="border-left:4px solid #a8842e;padding-left:12px">⭐ Für dich <span class="cnt"></span></h2>\n'
  '  <div class="grid"></div>\n'
  '  <p class="fdempty">Für dich ist noch keine persönliche Auswahl hinterlegt. Sag kurz in deiner WhatsApp-Gruppe Bescheid – dann richten wir sie ein.</p>\n'
  '</section>\n\n')

FD_JS = r'''
  /* ---- Personalisierte "Fuer dich"-Auswahl: pro Login-Passwort, nur Job-Kriterien ---- */
  var PROFILES={
   "lisamaria26":{ber:{buero:3,start:1,sprache:0.5,service:0},
     plus:["office","back office","backoffice","verwaltung","administration","sachbearbeit","assistenz","teamassistenz","projektassistenz","executive assistant","personal assistant","koordination","coordinator","disposition","auftragsabwicklung","datenerfassung","data entry","dateneingabe","dokumenten","organisation","office manager","office administration","office assistant","operations","scheduling","order management"],
     minus:["kundenservice","kundensupport","kundenkontakt","kundenbetreuung","kundendienst","customer service","customer support","customer care","customer success","guest","hospitality","hotel","reservation","concierge","call center","callcenter","telefonie","inbound","outbound","chat support","live chat","help desk","helpdesk","support agent","beschwerde","developer","engineer","software","vertrieb","sales","closer","setter","designer","marketing","crypto","blockchain","devops","rater","annotation","ai training"],
     hard:["developer","software engineer","devops","data engineer","qa engineer"],langs:["de","en"],reg:{world:3,eu:2,de:0}},
   "annette26":{ber:{service:3,buero:2,start:0.5},
     plus:["customer","support","kundenservice","kundensupport","kundenbetreuung","kundenberater","kundendienst","betreuung","service","technischer support","technischer kundenservice","assistant","assistenz","virtual assistant","office","back office","administration","verwaltung","operations","koordination","coordinator","data entry","sachbearbeit","empfang"],
     minus:["developer","engineer","software","buchhaltung","accounting","steuer","datev","closer","setter","direct sales","außendienst","designer","devops","controlling","lohn","bilanz","wirtschaftsprüf"],
     hard:["developer","software engineer","devops","buchhalt","steuerber","steuerfach","bilanzbuch","lohnbuchhalt","datev","accountant","accounting","bookkeep"],langs:["de","en"],reg:{world:3,eu:2,de:0}},
   "francesco26":{ber:{service:3,buero:2,start:0.5},
     plus:["kundenservice","kundensupport","kundenbetreuung","kundendienst","kundenberater","customer support","customer service","chat support","email support","technischer support","technischer kundenservice","helpdesk","it-support","1st level","first level","content moderat","moderator","support agent","betreuung","backoffice","back office","sachbearbeit","datenerfassung","data entry","auftragsabwicklung","versand","verwaltung","assistenz","office"],
     minus:["sales","closer","setter","outbound","kaltakquise","telefonverkauf","designer","marketing","seo","provision"],
     hard:["vertrieb","sales development","account executive","business development","sdr","sales manager","sales representative","außendienst","akquise","developer","software engineer","devops","data scientist","data engineer"],langs:["de"],reg:{world:3,eu:2,de:0}},
   "stefanie26":{ber:{buero:3,start:2,service:1},
     plus:["buchhaltung","accounting","steuer","datev","lohn","bilanz","finanz","controlling","rechnungswesen","sachbearbeit","office","verwaltung","back office"],
     minus:["developer","engineer","software","vertrieb","sales","closer","designer","marketing","devops"],
     hard:["developer","software engineer","devops"],langs:["de","en"],reg:{world:2,eu:2,de:2}}
  };
  function fdRegion(c){var t=(c.querySelector('.meta')||c).textContent;if(/Weltweit|🌍/.test(t))return'world';if(/EU|🇪🇺|Europa/.test(t))return'eu';return'de';}
  function fdText(c){return (((c.querySelector('h3')||{}).textContent||'')+' '+((c.querySelector('.info')||{}).textContent||'')+' '+((c.querySelector('.company')||{}).textContent||'')).toLowerCase();}
  function fdScore(c,p){
    var title=((c.querySelector('h3')||{}).textContent||'').toLowerCase();
    for(var i=0;i<p.hard.length;i++){if(title.indexOf(p.hard[i])>-1)return -999;}
    var s=0,t=fdText(c),ber=c.dataset.bereich||'';
    s+=(p.ber[ber]||0);
    var ph=0;for(var j=0;j<p.plus.length;j++){if(t.indexOf(p.plus[j])>-1)ph++;}s+=Math.min(ph*1.4,5.5);
    var mh=0;for(var k=0;k<p.minus.length;k++){if(t.indexOf(p.minus[k])>-1)mh++;}s-=mh*2.2;
    s+=(p.reg[fdRegion(c)]||0);
    if(p.langs.indexOf(c.dataset.lang)>-1)s+=1;
    if(c.dataset.lang==='de')s+=0.6;
    if(c.dataset.level==='einsteiger')s+=0.4;
    return s;
  }
  function fdStars(s){var n=(s>=10?5:(s>=8?4:(s>=6?3:(s>=4?2:1))));var o='';for(var i=0;i<5;i++)o+=(i<n?'★':'☆');return o;}
  function buildFD(){
    var sec=document.getElementById('fuerdich');if(!sec)return;
    var grid=sec.querySelector('.grid');var empty=sec.querySelector('.fdempty');var cnt=sec.querySelector('h2 .cnt');
    grid.innerHTML='';var p=PROFILES[CUR];
    if(!p){if(empty)empty.style.display='block';if(cnt)cnt.textContent='';return;}
    var arr=[];
    document.querySelectorAll('.card').forEach(function(c){
      if(c.closest('#favoriten')||c.closest('#toolbox')||c.closest('#freelance')||c.closest('#fuerdich'))return;
      var s=fdScore(c,p);if(s>-900)arr.push({c:c,s:s});
    });
    arr.sort(function(a,b){return b.s-a.s;});
    var sel=arr.filter(function(o){return o.s>=6;});   /* alle Treffer mit >=3 von 5 Sternen */
    if(sel.length<50)sel=arr.slice(0,50);              /* aber immer mindestens 50 */
    sel.forEach(function(o){
      var cl=o.c.cloneNode(true);cl.classList.remove('hidden');
      var badge=document.createElement('div');badge.className='fdfit';
      badge.style.cssText='font-size:11px;font-weight:800;color:#a8842e;letter-spacing:.06em;margin:2px 0 8px';
      badge.textContent='PASST ZU DIR  '+fdStars(o.s);
      cl.insertBefore(badge,cl.firstChild);
      grid.appendChild(cl);
    });
    if(empty)empty.style.display=sel.length?'none':'block';
    if(cnt)cnt.textContent=sel.length?(sel.length+' passende Treffer für dich'):'';
    paintStars();
  }
  function activateFDForUser(){
    var chip=document.querySelector('.chip[data-f="fd"]');if(!chip)return;
    if(PROFILES[CUR]){
      chip.style.display='';
      try{
        document.querySelectorAll('.chip:not(.lv):not(.langf):not(.directf)').forEach(function(x){x.classList.remove('active');});
        chip.classList.add('active');active='fd';apply();
        try{var _fd=document.getElementById('fuerdich');var _tb=document.querySelector('.toolbar');var _off=_tb?_tb.offsetHeight:0;var _y=_fd.getBoundingClientRect().top+window.pageYOffset-_off-8;window.scrollTo(0,Math.max(0,_y));}catch(_s){}   /* auf die Treffer scrollen, nicht auf leeren Header */
      }catch(e){ active='all'; try{apply();}catch(_){ } }   /* Fallback: nie das Board zerschiessen */
    }else{chip.style.display='none';}
  }
'''

def _inject_fd(head, tail):
    """Injiziert Chip + Sektion + Scoring-JS in die Shell. Fehlt ein Anker (Template
    geaendert), wird gewarnt und ohne die Personalisierung gebaut (Board bleibt heil)."""
    def rep(s, old, new, tag):
        if old in s: return s.replace(old, new, 1)
        print(f"[fd] WARN Anker fehlt ({tag}) - Teil nicht injiziert"); return s
    # Chip vor "Alle"
    head = rep(head, '<span class="chip active" data-f="all">Alle</span>',
               FD_CHIP + '<span class="chip active" data-f="all">Alle</span>', "chip")
    # Breiten-Fix fuer #fuerdich/#favoriten (CSS ins <head>)
    if '</head>' in head: head = head.replace('</head>', FD_CSS + '</head>', 1)
    else: head = FD_CSS + head
    # Sektion vor #freelance (tail beginnt damit)
    idx = tail.find('<section id="freelance"')
    if idx >= 0: tail = tail[:idx] + FD_SECTION + tail[idx:]
    else: print("[fd] WARN Anker fehlt (freelance) - Sektion nicht injiziert")
    # JS-Definitionen nach 'var CUR'
    tail = rep(tail, "var CUR='';", "var CUR='';" + FD_JS, "cur")
    # unlock() ruft activateFDForUser()
    tail = rep(tail,
        "function unlock(){\n    document.getElementById('gate').style.display='none';\n    document.getElementById('app').style.display='block';\n    paintStars();\n  }",
        "function unlock(){\n    document.getElementById('gate').style.display='none';\n    document.getElementById('app').style.display='block';\n    paintStars();\n    try{activateFDForUser();}catch(e){}\n  }",
        "unlock")
    # apply(): fd-Zweig
    tail = rep(tail, "    if(active==='fav'){",
        "    var fdS=document.getElementById('fuerdich'); if(fdS)fdS.classList.add('hidden');\n"
        "    if(active==='fd'){ buildFD(); sects.forEach(function(s2){s2.classList.add('hidden');}); if(fdS)fdS.classList.remove('hidden'); return; }\n"
        "    if(active==='fav'){", "apply-fd")
    # Normalansicht: #fuerdich nicht mit einblenden
    tail = rep(tail, "sects.forEach(function(s2){if(s2!==tb && s2!==fav)s2.classList.remove('hidden');});",
        "sects.forEach(function(s2){if(s2!==tb && s2!==fav && s2.id!=='fuerdich')s2.classList.remove('hidden');});", "show")
    # leere-Sektion-Schleife: fuerdich ueberspringen
    tail = rep(tail, "if(sec.id==='toolbox'||sec.id==='favoriten')return;",
        "if(sec.id==='toolbox'||sec.id==='favoriten'||sec.id==='fuerdich')return;", "emptyskip")
    # buildFav: fuerdich-Klone nicht mitzaehlen
    tail = rep(tail, "if(c.closest('#favoriten')||c.closest('#toolbox'))return;",
        "if(c.closest('#favoriten')||c.closest('#toolbox')||c.closest('#fuerdich'))return;", "favskip")
    return head, tail

def build_sections(jobs):
    by={b:[] for b in BEREICH_ORDER}
    for j in jobs: by[j["bereich"]].append(j)
    for b in by:  # Kunden + Importe immer behalten, nur Auto (Feed) deckeln
        keep=[j for j in by[b] if j.get("src")!="auto"]
        au=[j for j in by[b] if j.get("src")=="auto"]
        au.sort(key=_rank)                                   # beim Deckeln deutsch+direkte Auto-Jobs bevorzugt behalten
        sel = keep + au[:max(0, CAP.get(b,60)-len(keep))]
        sel.sort(key=_rank)                                  # ANZEIGE: deutsch+direkte Stellen ganz oben, ⭐ zuerst
        by[b]=sel
    html=[]
    for ber,color,label in BEREICHE:
        cards=by[ber]
        if not cards: continue
        html.append(f'<section data-ber="{ber}"><h2 style="border-left:4px solid {color};padding-left:12px">{label} <span class="cnt">{len(cards)} Stellen</span></h2>\n<div class="grid">\n'
                    + "\n".join(card(c) for c in cards) + "\n</div>\n</div></section>")
    return "\n\n".join(html), by

def main():
    tpl=open(TEMPLATE,encoding="utf-8").read()
    i0=tpl.find('<section data-ber="service"')
    i1=tpl.find('<section id="freelance"')
    assert i0>0 and i1>0, "Template-Grenzen nicht gefunden"
    head, tail = tpl[:i0], tpl[i1:]
    head, tail = _inject_fd(head, tail)   # personalisierte "Fuer dich"-Ansicht einbauen

    auto=process(gather())
    manual=load_manual()
    ats=gather_ats()   # echte deutschsprachige Remote-Einzelstellen direkt von Firmen-Boards
    if ats: print(f"[ats] GESAMT: {len(ats)} deutschsprachige Remote-Einzelstellen von Firmen-Boards")
    manual = manual + ats   # ATS wie manuelle Schicht: nie gedeckelt, im Deutsch-Pool
    # (Tote-Link-Check + Redirect-Aufloesung laufen jetzt board-weit weiter unten, ueber ALLE Stellen.)

    man_urls={m["url"].rstrip("/") for m in manual}
    auto=[a for a in auto if a["url"].rstrip("/") not in man_urls]  # manuell gewinnt

    # --- Paul-Vorgabe: mindestens die Haelfte deutschsprachig (ueber das GANZE Board) ---
    # Kunden-Picks immer behalten; Englisch nur so weit, dass insgesamt Deutsch >= Englisch.
    # Pool-Reihenfolge: Importe (kuratiert) vor Auto (Feed) -> Feed-Englisch wird zuerst gekuerzt.
    # Lauf #20 (Paul: mehr Volumen): KEINE Deutsch-Quote mehr, die Englisch kuerzt.
    # Der CAP pro Bereich + die Sortierung (weltweit+deutsch+direkt oben) regeln den Mix.
    cust=[m for m in manual if m["src"]=="customer"]
    pool=[m for m in manual if m["src"]!="customer"] + auto
    alljobs=cust+pool
    # Paul #22: Karriere-/Boersen-/Kategorieseiten KOMPLETT ausstreichen ("immer direkt auf die Stelle,
    # nicht auf irgendeine Karriere-Seite"). In den 7 Bereichen bleiben NUR noch echte Direkt-Einzelstellen -
    # auch bei den ⭐-Kundenpicks. Ersatz-Deckung fuer die Kunden liefert die ATS-Engine (zieht die
    # aktuellen Direkt-Links der Firmen automatisch) + die verbleibenden Direkt-Picks.
    # (Die statischen Freelance-/Toolbox-Sektionen im Template bleiben unberuehrt.)
    _before=len(alljobs)
    _dropped=[j for j in alljobs if not is_direct(j["url"])]
    alljobs=[j for j in alljobs if is_direct(j["url"])]
    print(f"[direkt] Karriere-/Boersenseiten entfernt: {_before-len(alljobs)} -> {len(alljobs)} bleiben (NUR Direkt-Einzelstellen)")
    _dfd=sum(1 for j in _dropped if j.get("fd"))
    print(f"[direkt] davon {_dfd} entfernte ⭐-Kundenpicks (Karriereseiten) - Deckung via ATS-Engine + Direkt-Picks")

    # Titel+Firma-Dedup (Paul: viele Wiederholungen). URL-Dedup greift nicht, wenn Adzuna dieselbe Stelle
    # in mehreren Laendern (de/at/ch) mit verschiedenen redirect-URLs listet. Erst-gesehen gewinnt
    # (Kunden-Picks + manuelle + Direkt-Feeds stehen vor Adzuna im Pool -> die echte Direktstelle bleibt).
    def _dupkey(j):
        t=re.sub(r"\(.*?\)"," ",(j.get("title") or "").lower())        # (m/w/d), (100% remote) ... raus
        t=re.sub(r"[^a-z0-9]+"," ",t).strip()
        c=re.sub(r"[^a-z0-9]+"," ",(j.get("company") or "").lower()).strip()
        return (t+"|"+c) if (t and c) else None   # NUR mit echter Firma mergen (kein Titel-only-Merge -> keine Fehl-Dubletten)
    _rrank={"world":2,"eu":1,"de":0}
    _best={}; _keep=[True]*len(alljobs)
    for i,j in enumerate(alljobs):
        k=_dupkey(j)
        if not k: continue                          # ohne echte Firma: nie als Dublette werfen
        if k in _best:
            pi=_best[k]
            # Bei Dublette die Weltweit-/bessere-Region-Version behalten (Paul: 100% remote weltweit = Goldstueck, NIE wegwerfen).
            if _rrank.get(j.get("region"),0) > _rrank.get(alljobs[pi].get("region"),0):
                _keep[pi]=False; _best[k]=i
            else:
                _keep[i]=False
        else:
            _best[k]=i
    _dd=[j for j,kp in zip(alljobs,_keep) if kp]
    print(f"[dedup] Titel+Firma-Dubletten entfernt: {len(alljobs)-len(_dd)} -> {len(_dd)} bleiben (Weltweit-Version bevorzugt)")
    alljobs=_dd

    # Board-weit (Paul-Wunsch): Portal-/Redirect-URLs (Adzuna & Co) auf die ECHTE Einzelstelle aufloesen,
    # damit der Kandidat direkt auf der Anzeige landet; sicher-tote Links (404/410) komplett raus.
    alljobs, dead, resolved = resolve_and_prune(alljobs)
    print(f"[links] {resolved} Portal-Links direkt aufgeloest, {dead} tote (404/410) raus -> {len(alljobs)} echte, lebende Direkt-Stellen")

    sections, by = build_sections(alljobs)
    total=len(alljobs); de=sum(1 for j in alljobs if j["lang"]=="de")
    world=sum(1 for j in alljobs if j["region"]=="world"); einst=sum(1 for j in alljobs if j["level"]=="einsteiger")

    # Stats im Head aktualisieren
    def setstat(label,val):
        nonlocal head
        head=re.sub(r'(<b>)\d+(</b><span>'+re.escape(label)+r')', r'\g<1>'+str(val)+r'\2', head, count=1)
    setstat("Positionen aktuell",total); setstat("weltweit machbar",world)
    setstat("Einsteiger-geeignet",einst); setstat("auf Deutsch",de)

    open(OUT,"w",encoding="utf-8").write(head+sections+"\n\n"+tail)
    pct = round(100*de/total) if total else 0
    n_c=sum(1 for j in alljobs if j.get("src")=="customer")
    n_i=sum(1 for j in alljobs if j.get("src")=="import")
    n_a=sum(1 for j in alljobs if j.get("src")=="auto")
    n_ats=sum(1 for j in alljobs if j.get("src")=="ats")
    print(f"\nGEBAUT: {total} Stellen | de={de} ({pct}%) en={total-de} weltweit={world} einsteiger={einst}")
    print(f"   Kunden {n_c} + Import {n_i} + Auto {n_a} + ATS-Direktstellen {n_ats} | tote Links entfernt: {dead}")
    for b,_,lbl in BEREICHE: print(f"   {lbl}: {len(by[b])}")
    print("->", OUT)

if __name__=="__main__":
    main()

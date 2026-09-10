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
import json, re, sys, os, datetime, urllib.request, urllib.error

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
    "service":  ["kundenservice","kundenbetreu","customer support","customer service","customer care","customer success","customer experience","customer advocate","support agent","support specialist","support consultant","support representative","support engineer","technical support","chat support","live chat","email support","help desk","helpdesk","service agent","client support","member support","player support","guest","reservation","booking","reise","travel","hospitality","concierge","call center","callcenter","kundenberat","beschwerde","content moderat","trust and safety","trust & safety","happiness engineer","community support","onboarding specialist","tier 1","tier 2"],
    "buero":    ["buchhalt","accounting","accountant","finance","finanzbuch","lohn","payroll","steuerfach","controlling","sachbearbeit","backoffice","back office","back-office","assistenz","assistant","virtual assistant","executive assistant","personal assistant","verwaltung","admin","office manager","operations specialist","operations coordinator","operations associate","customer operations","people operations","coordinator","scheduling","order management","datenerfassung","data entry","dateneingabe"],
    "start":    [],   # frueher Mikrojobs - jetzt raus (Paul). Sektion zeigt nur noch manuelle Freelance-/Portal-Eintraege.
    "sprache":  ["übersetz","ubersetz","translat","lektor","proofread","texter","content writer","copywriter","redaktion","tutor","nachhilfe","language teacher","sprachlehrer"],
    "marketing":["marketing","social media","seo","content creator","content manager","grafik","design","designer","creative","video","brand","paid ads","performance market","kampagne","community manager"],
    "vertrieb": ["sales","vertrieb","sdr","sales development","setter","closer","business development","account executive","akquise","inside sales"],
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
    "data annotation","datenannotation","annotator","data labeling","data labelling","daten labeln","rater","search evaluator","ads rating",
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
    else: region = "de"   # ohne expliziten Weltweit-/EU-Marker: als Deutschland-nur behandeln (-> wird gefiltert)
    level = "einsteiger" if any(m in t for m in EINSTEIGER_MARKERS) else "erfahren"
    return lang, region, level

# ---------- Feeds ----------
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"})
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

def http_text(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"})
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
    # --- Neue Quellen (aus dem Hauptboard uebernommen, fuer die Zukunft) ---
    ("realworkfromanywhere","https://www.realworkfromanywhere.com/feed", from_rss_generic, "text"),
    ("euremotejobs",  "https://euremotejobs.com/feed/",                  from_rss_generic, "text"),
    ("nodesk",        "https://nodesk.co/remote-jobs/feed/",             from_rss_generic, "text"),
    ("jobspresso",    "https://jobspresso.co/remote-work/feed/",         from_rss_generic, "text"),
    ("remote3",       "https://remote3.co/feed",                         from_rss_generic, "text"),
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
    ("remoteok-cs",           "https://remoteok.com/remote-customer-support-jobs.rss", from_rss_generic, "text"),
    ("remoteok-nontech",      "https://remoteok.com/remote-non-tech-jobs.rss",         from_rss_generic, "text"),
    ("remotewoman",           "https://remotewoman.com/feed/",                         from_rss_generic, "text"),
    ("jobicy-rss",            "https://jobicy.com/?feed=job_feed",                     from_rss_generic, "text"),
    ("dailyremote",           "https://dailyremote.com/feed",                          from_rss_generic, "text"),
    # --- Lauf #19: neue Boards + gezielt Reise/Hospitality (Paul-Wunsch) ---
    ("remotive-hospitality",  "https://remotive.com/api/remote-jobs?search=hospitality", from_remotive, "json"),
    ("remotive-guest",        "https://remotive.com/api/remote-jobs?search=guest%20experience", from_remotive, "json"),
    ("remotive-booking",      "https://remotive.com/api/remote-jobs?search=booking",     from_remotive, "json"),
    ("remotive-concierge",    "https://remotive.com/api/remote-jobs?search=concierge",   from_remotive, "json"),
    ("jobicy-anywhere2",      "https://jobicy.com/api/v2/remote-jobs?count=100&geo=anywhere&industry=supporting", from_jobicy, "json"),
    ("remoteok-worldwide",    "https://remoteok.com/remote-worldwide-jobs.rss",          from_rss_generic, "text"),
    ("remoteok-travel",       "https://remoteok.com/remote-travel-jobs.rss",             from_rss_generic, "text"),
    ("dynamitejobs",          "https://dynamitejobs.com/feed",                          from_rss_generic, "text"),
    ("cryptojobslist",        "https://cryptojobslist.com/feed",                        from_rss_generic, "text"),
    ("remote-co",             "https://remote.co/remote-jobs/feed/",                     from_rss_generic, "text"),
    ("pangian",               "https://pangian.com/job-board/feed/",                     from_rss_generic, "text"),
    # --- Lauf #21: mehr kundennahe/deutsche Suchen (mehr Direkt-Einzelstellen) ---
    ("remotive-success",      "https://remotive.com/api/remote-jobs?search=customer%20success", from_remotive, "json"),
    ("remotive-va",           "https://remotive.com/api/remote-jobs?search=virtual%20assistant", from_remotive, "json"),
    ("remotive-moderator",    "https://remotive.com/api/remote-jobs?search=moderator",   from_remotive, "json"),
    ("remotive-onboarding",   "https://remotive.com/api/remote-jobs?search=onboarding",  from_remotive, "json"),
    ("remotive-german3",      "https://remotive.com/api/remote-jobs?search=deutschsprachig", from_remotive, "json"),
    ("jobicy-de2",            "https://jobicy.com/api/v2/remote-jobs?count=100&tag=deutsch", from_jobicy, "json"),
    ("remoteok-support",      "https://remoteok.com/remote-customer-support-jobs.rss",   from_rss_generic, "text"),
]

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
    """True = Link fuehrt direkt zur Einzelstelle. False = Firmen-/Boersen-Karriereseite (Liste)."""
    s=(url or "").lower().rstrip("/")
    path=re.sub(r"^https?://[^/]+","",s)
    if path=="": return False
    # generische Landing-/Karriereseiten -> keine Einzelstelle
    if re.search(r"/(careers?|jobs|hire|karriere|career|job-vacancies|vacancies|stellenangebote|stellen|join|openings|positions|offene-stellen|all-jobs)$", path): return False
    # Kategorie-/Boersen-Seiten (z.B. yeahbase /jobs/setter/remote, top-closer /jobs/appointment-setter)
    if re.search(r"/jobs?/(setter|closer|remote|homeoffice|appointment-setter|closer-deutschland|high-ticket)(/|$)", path): return False
    if "?title=" in s or s.endswith("/jobs") or s.endswith("/career"): return False
    # Einzelstellen-Signale
    if re.search(r"\d{5,}", path): return True                                  # numerische Job-ID
    if re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}", path): return True      # UUID (lever/greenhouse)
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
CAP={"service":500,"buero":250,"start":200,"sprache":180,"marketing":120,"vertrieb":120,"it":120}
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

    auto=process(gather())
    manual=load_manual()
    ats=gather_ats()   # echte deutschsprachige Remote-Einzelstellen direkt von Firmen-Boards
    if ats: print(f"[ats] GESAMT: {len(ats)} deutschsprachige Remote-Einzelstellen von Firmen-Boards")
    manual = manual + ats   # ATS wie manuelle Schicht: nie gedeckelt, im Deutsch-Pool, wird link-gecheckt
    # Tote Links in der manuellen/Import-Schicht raus (laeuft auf GitHub mit offenem Netz)
    manual, dead = prune_dead(manual)
    print(f"[linkcheck] manuelle Schicht: {dead} tote Links entfernt -> {len(manual)} bleiben")

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
    # Paul #21: Firmen-/Karriereseiten fast ausstreichen. In den 7 Bereichen nur noch DIREKT-Stellen
    # (Link fuehrt direkt zur Anzeige) + die kuratierten ⭐-Kundenpicks. Nicht-direkte Nicht-Picks raus.
    # (Die statischen Freelance-/Toolbox-Sektionen im Template bleiben unberuehrt.)
    _before=len(alljobs)
    alljobs=[j for j in alljobs if is_direct(j["url"]) or j.get("fd")]
    print(f"[direkt] Firmen-/Karriereseiten entfernt: {_before-len(alljobs)} -> {len(alljobs)} bleiben (nur Direkt + ⭐-Picks)")

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

"""Clean contact fields and reconcile the recommended mailbox with the addressee.

Statuses written to each row as match_status / match_action:
  ящик общий       – role/office mailbox, addressee is the responsible officer (fine)
  личный, совпало  – personal mailbox whose owner is the named addressee (fine)
  нет имени        – mailbox exists, no addressee name (neutral salutation is used)
  нет ящика        – no usable mailbox
  ПРОВЕРИТЬ        – personal-looking mailbox, name does not match the owner (needs a human/browser)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from build_xlsx import EMAIL_RE, WEAK_MAILBOX, outreach_email  # noqa: E402

DATA = os.path.join(HERE, "data")
FILES = ["china", "india", "brazil", "south_africa", "uae", "egypt", "iran", "indonesia",
         "saudi_arabia", "ethiopia", "partners", "russia"]
GEN = re.compile(r"info|international|intl|inter|oia|oir|oie|ioa|iro|fao|global|office|admission|contact|mail|"
                 r"registrar|president|rector|reitor|vicechancellor|vice-chancellor|^vc|vc$|dean|director|gabinete|"
                 r"secret|press|news|cooperat|relation|exchange|partner|outreach|liaison|external|engage|affairs|"
                 r"principal|reitoria|rektor|humas|reception|enquir|support|help|admin|kui|kerjasama|waiban|waishi|"
                 r"gjc|gjhz|gjjl|guohe|guoji|foreign|student|iao|cir$|dri$|ari$|sri$|cori|crint|cri$|oiec|oge|ipo", re.I)
PERSONAL_NOTE = re.compile(r"личн(ый|ая|ого|ым)\s+(ящик|адрес|e-?mail|почт)|персональн|named (staff|person)|"
                           r"именн|personal (mailbox|e-?mail|address)|ящик сотрудника|адрес сотрудника", re.I)
URL = re.compile(r"https?://[^\s;,()]+")
# Genuine duplicates only (same institution listed twice); name -> the row that is kept.
DUPLICATES = {
    ("indonesia", "Universitas Hasanuddin (Unhas)"): "Hasanuddin University (Unhas)",
    ("india", "UPES (University of Petroleum and Energy Studies)"): "University of Petroleum and Energy Studies",
}
INTL = re.compile(r"international|intl|inter|oia|oir|oie|ioa|iro|fao|global|cooperat|exchange|relation|foreign|ari$|dri$|sri$|cori|crint|gjc|gjjl|gjhz|guoji|waiban|waishi|kui|kerjasama|iao|oiec", re.I)


def clean_email_field(r, key):
    v = (r.get(key) or "").strip()
    if not v:
        return False
    found = EMAIL_RE.findall(v)
    if not found:
        return False
    if v == found[0]:
        return False
    r.setdefault("notes_ru", []).append(f"Поле e-mail ({key}) очищено; исходная запись: {v[:200]}")
    r[key] = found[0]
    return True


def clean_site(r):
    w = (r.get("website") or "").strip()
    if not w:
        return False
    m = re.match(r"\s*(https?://[^\s;,()]+|[\w.-]+\.[a-z]{2,}[^\s;,()]*)", w)
    if not m:
        return False
    tok = m.group(1).rstrip("/.,;")
    if not tok.startswith("http"):
        tok = "https://" + tok
    if tok == w:
        return False
    extra = [u for u in URL.findall(w) if u.rstrip("/") != tok.rstrip("/")]
    if extra:
        r.setdefault("notes_ru", []).append("Дополнительные сайты: " + ", ".join(extra))
    r["website"] = tok
    return True


def toks(nm):
    nm = re.sub(r"\(.*?\)", "", nm or "")
    return [t.lower().replace("'", "") for t in re.findall(r"[A-Za-zÀ-ÿ']{3,}", nm)]


def is_personal(r, mail):
    lp = mail.split("@")[0].lower()
    if len(lp) <= 5:
        return False
    notes = " ".join(r.get("notes_ru") or []) + " " + (r.get("mailbox_owner") or "")
    flagged = bool(PERSONAL_NOTE.search(notes)) and lp in notes.lower()
    shaped = bool(re.search(r"\d{3,}|^[a-z]\.[a-z]{3,}$|^[a-z]{3,}\.[a-z]$|^[a-z]{3,}[._][a-z]{3,}$", lp)) and not GEN.search(lp)
    plain = (not GEN.search(lp)) and len(lp) >= 6
    return flagged or shaped or plain


def status(r):
    mail = outreach_email(r)
    nm = (r.get("addressee_name") or "").strip()
    if not mail:
        return "нет ящика", "Найти e-mail международного отдела или канцелярии"
    if not nm:
        return "нет имени", "Письмо с нейтральным обращением; имя найти при проверке сайта"
    if WEAK_MAILBOX.match(mail.split("@")[0]):
        return "ПРОВЕРИТЬ", "Ящик приёмной комиссии/вебмастера — найти ящик международного отдела"
    if not is_personal(r, mail):
        return "ящик общий", ""
    if any(t in mail.split("@")[0].lower() for t in toks(nm)):
        return "личный, совпало", ""
    return "ПРОВЕРИТЬ", "Ящик личный, имя адресата не совпадает с владельцем — уточнить владельца ящика"


def alternative(r):
    """A role mailbox among the other candidate fields that can replace a personal one."""
    cur = outreach_email(r).lower()
    for key in ("email_international", "email_general"):
        for m in EMAIL_RE.findall(r.get(key) or ""):
            lp = m.split("@")[0].lower()
            if m.lower() != cur and not WEAK_MAILBOX.match(lp) and GEN.search(lp) and not re.search(r"webmaster|noreply", lp):
                return m
    return ""


def main():
    stats = {"site": 0, "email": 0, "swapped": 0, "dedup": 0, "sal": 0}
    report = []
    for f in FILES:
        path = os.path.join(DATA, f + ".json")
        rows = json.load(open(path, encoding="utf-8"))
        keep = []
        for r in rows:
            if (f, r["name_en"]) in DUPLICATES:
                report.append((f, "дубль удалён", r["name_en"], DUPLICATES[(f, r["name_en"])]))
                stats["dedup"] += 1
                continue
            keep.append(r)
        rows = keep
        for r in rows:
            stats["site"] += clean_site(r)
            stats["email"] += clean_email_field(r, "email_general") + clean_email_field(r, "email_international")
            st, act = status(r)
            if st == "ПРОВЕРИТЬ":
                alt = alternative(r)
                # swap only for a mailbox of the same function (international office) or when the current one is weak
                weak = bool(WEAK_MAILBOX.match(outreach_email(r).split("@")[0]))
                if alt and (weak or INTL.search(alt.split("@")[0])):
                    r["outreach_email_new"] = alt
                    r.setdefault("notes_ru", []).append(f"Для рассылки выбран общий ящик {alt} вместо личного/служебного")
                    stats["swapped"] += 1
                    st, act = status(r)
            r["match_status"], r["match_action"] = st, act
            if st == "ПРОВЕРИТЬ":
                report.append((f, "проверить", r["name_en"], outreach_email(r) + " | " + (r.get("addressee_name") or "")))
        json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(stats)
    return report


if __name__ == "__main__":
    rep = main()
    for x in rep:
        if x[1] == "дубль удалён":
            print(x)
    print(sum(1 for x in rep if x[1] == "проверить"), "строк со статусом ПРОВЕРИТЬ")

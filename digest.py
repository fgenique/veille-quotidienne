#!/usr/bin/env python3
"""
Veille quotidienne — script principal.

Ce script :
  1. lit les thèmes choisis dans config.yaml ;
  2. va chercher, pour chaque thème, le(s) meilleur(s) article(s)
     en français et en anglais publiés récemment (via les flux RSS
     de Google Actualités, gratuits et sans clé d'API) ;
  3. génère une page web (docs/index.html) destinée à GitHub Pages ;
  4. envoie une notification (Telegram et/ou e-mail, selon ce qui
     est configuré) avec le contenu de la veille et le lien vers
     la page complète.

Il est pensé pour être lancé une fois par jour par GitHub Actions,
mais fonctionne aussi très bien en local : `python digest.py`.
"""

from __future__ import annotations

import html
import os
import smtplib
import sys
import time
import datetime as dt
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests
import yaml

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"

# Paramètres régionaux pour chaque langue demandée.
LANG_SETTINGS = {
    "fr": {"hl": "fr", "gl": "FR", "ceid": "FR:fr", "flag": "🇫🇷", "label": "Français"},
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en", "flag": "🇬🇧", "label": "English"},
}

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VeilleQuotidienne/1.0)"}
REQUEST_TIMEOUT = 12
DELAY_BETWEEN_REQUESTS = 1.0  # secondes, pour rester poli avec Google News


# --------------------------------------------------------------------------
# Récupération des articles
# --------------------------------------------------------------------------

def build_rss_url(topic: str, lang: str, lookback_days: int) -> str:
    """Construit l'URL du flux RSS Google Actualités pour un thème/langue donnés."""
    settings = LANG_SETTINGS[lang]
    query = f"{topic} when:{lookback_days}d"
    return GOOGLE_NEWS_RSS.format(
        query=quote_plus(query),
        hl=settings["hl"],
        gl=settings["gl"],
        ceid=settings["ceid"],
    )


def parse_rss_items(xml_bytes: bytes) -> list[dict]:
    """Extrait les articles (titre, lien, source, date) d'un flux RSS."""
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        source_el = item.find("source")

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        pubdate = (pubdate_el.text or "").strip() if pubdate_el is not None else ""
        source = (source_el.text or "").strip() if source_el is not None else ""

        if not title or not link:
            continue

        # Google Actualités ajoute souvent "... - Nom de la source" au titre.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()

        items.append({"title": title, "link": link, "source": source, "pubdate": pubdate})
    return items


def fetch_articles(topic: str, lang: str, lookback_days: int, count: int) -> list[dict]:
    """Va chercher les `count` meilleurs articles pour un thème et une langue."""
    url = build_rss_url(topic, lang, lookback_days)
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! Erreur réseau pour « {topic} » ({lang}) : {exc}", file=sys.stderr)
        return []

    try:
        items = parse_rss_items(response.content)
    except ET.ParseError as exc:
        print(f"  ! Flux RSS illisible pour « {topic} » ({lang}) : {exc}", file=sys.stderr)
        return []

    return items[:count]


def format_relative_time(pubdate: str, lang: str) -> str:
    """Transforme une date RSS ('Mon, 22 Sep 2026 08:00:00 GMT') en '3 h' / '3h ago'."""
    if not pubdate:
        return ""
    try:
        published = parsedate_to_datetime(pubdate)
        if published.tzinfo is None:
            published = published.replace(tzinfo=dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        delta_minutes = max(1, int((now - published).total_seconds() // 60))
    except (TypeError, ValueError):
        return ""

    if delta_minutes < 60:
        return f"il y a {delta_minutes} min" if lang == "fr" else f"{delta_minutes} min ago"
    delta_hours = delta_minutes // 60
    if delta_hours < 24:
        return f"il y a {delta_hours} h" if lang == "fr" else f"{delta_hours}h ago"
    delta_days = delta_hours // 24
    return f"il y a {delta_days} j" if lang == "fr" else f"{delta_days}d ago"


def build_digest(config: dict) -> list[dict]:
    """Construit la veille complète : liste de {topic, fr: [...], en: [...]}."""
    topics = config.get("topics", [])
    lookback_days = int(config.get("lookback_days", 1))
    count = int(config.get("articles_per_topic", 1))

    digest = []
    for topic in topics:
        print(f"Recherche des actus pour « {topic} »...")
        entry = {"topic": topic}
        for lang in ("fr", "en"):
            articles = fetch_articles(topic, lang, lookback_days, count)
            for article in articles:
                article["relative_time"] = format_relative_time(article["pubdate"], lang)
            entry[lang] = articles
            time.sleep(DELAY_BETWEEN_REQUESTS)
        digest.append(entry)
    return digest


# --------------------------------------------------------------------------
# Génération de la page web (docs/index.html, servie par GitHub Pages)
# --------------------------------------------------------------------------

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Veille du {date_human}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,400;0,500;0,600;1,400;1,500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<!-- Tailwind via CDN : pas d'étape de build, fonctionne tel quel sur GitHub Pages. -->
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {{
    theme: {{
      extend: {{
        colors: {{
          bg: '#F1F3EF',
          paper: '#FFFFFF',
          ink: '#1B1F1D',
          muted: '#5B655E',
          'accent-fr': '#2F5233',
          'accent-en': '#8A5A2B',
          rule: '#D8DBD3',
        }},
        fontFamily: {{
          serif: ['Newsreader', 'Georgia', 'serif'],
          sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        }},
      }},
    }},
  }}
</script>
</head>
<body class="bg-bg text-ink font-sans antialiased">
  <div class="h-[5px] bg-accent-fr"></div>
  <main class="max-w-2xl mx-auto px-6 sm:px-8 py-14">
    <header class="mb-14">
      <h1 class="font-serif text-4xl sm:text-5xl leading-tight mb-3">Ta veille du {date_human}</h1>
      <p class="text-muted text-sm">Générée automatiquement — un article en français et un en anglais par thème</p>
    </header>
    {topics_html}
    <footer class="mt-16 pt-6 border-t border-rule text-muted text-xs">
      Page régénérée chaque jour par ton script — dépôt GitHub personnel.
    </footer>
  </main>
</body>
</html>
"""


def render_story(article: dict | None, lang: str) -> str:
    settings = LANG_SETTINGS[lang]
    accent = "accent-fr" if lang == "fr" else "accent-en"

    if not article:
        return f"""
        <article class="border-l-2 border-rule pl-4">
          <p class="text-xs font-semibold text-muted mb-1.5">{settings['label']}</p>
          <p class="text-[15px] italic text-muted">Aucun article trouvé pour l'instant.</p>
        </article>"""

    title = html.escape(article["title"])
    link = html.escape(article["link"], quote=True)
    meta_parts = [p for p in (article.get("source"), article.get("relative_time")) if p]
    meta = html.escape(", ".join(meta_parts))
    return f"""
        <article class="border-l-2 border-{accent} pl-4">
          <p class="text-xs font-semibold text-{accent} mb-1.5">{settings['label']}</p>
          <p class="text-[16px] leading-snug mb-1">
            <a href="{link}" class="text-ink underline decoration-rule underline-offset-2 hover:decoration-ink">{title}</a>
          </p>
          <p class="text-xs text-muted">{meta}</p>
        </article>"""


def render_topic(entry: dict, is_first: bool) -> str:
    topic_title = html.escape(entry["topic"])
    fr_articles = entry.get("fr") or [None]
    en_articles = entry.get("en") or [None]

    stories_html = "".join(render_story(a, "fr") for a in fr_articles)
    stories_html += "".join(render_story(a, "en") for a in en_articles)

    wrapper = "" if is_first else "mt-10 pt-10 border-t border-rule"
    return f"""
  <section class="{wrapper}">
    <h2 class="font-serif italic text-2xl mb-6">{topic_title}</h2>
    <div class="grid sm:grid-cols-2 gap-x-8 gap-y-6">{stories_html}
    </div>
  </section>"""


def render_html(digest: list[dict]) -> str:
    today = dt.date.today()
    date_human = today.strftime("%d/%m/%Y")
    topics_html = "".join(render_topic(entry, i == 0) for i, entry in enumerate(digest))
    return PAGE_TEMPLATE.format(date_human=date_human, topics_html=topics_html)


# --------------------------------------------------------------------------
# Génération de l'e-mail (gabarit dédié, différent de la page web)
#
# Les clients mail (Gmail, Outlook, Apple Mail...) ne supportent ni les
# polices Google Fonts externes, ni CSS grid/flexbox de façon fiable. On
# utilise donc : des tableaux pour la mise en page, des styles en ligne
# (pas de <style> externe indispensable), et des polices "web-safe" avec
# de bons équivalents (Georgia pour le serif, Helvetica/Arial pour le sans).
# La palette et l'esprit graphique restent les mêmes que la page web.
# --------------------------------------------------------------------------

EMAIL_INK = "#1B1F1D"
EMAIL_MUTED = "#5B655E"
EMAIL_BG = "#F1F3EF"
EMAIL_PAPER = "#FFFFFF"
EMAIL_ACCENT_FR = "#2F5233"
EMAIL_ACCENT_EN = "#8A5A2B"
EMAIL_RULE = "#D8DBD3"
EMAIL_SERIF = "Georgia, 'Times New Roman', Times, serif"
EMAIL_SANS = "Helvetica, Arial, sans-serif"


def render_email_story_row(article: dict | None, lang: str) -> str:
    settings = LANG_SETTINGS[lang]
    color = EMAIL_ACCENT_FR if lang == "fr" else EMAIL_ACCENT_EN

    if not article:
        return f"""
        <tr><td style="padding:0 0 22px 0;">
          <p style="margin:0 0 5px 0; font-family:{EMAIL_SANS}; font-size:12px; font-weight:bold; color:{color};">{settings['label']}</p>
          <p style="margin:0; font-family:{EMAIL_SANS}; font-size:15px; font-style:italic; color:{EMAIL_MUTED};">Aucun article trouvé pour l'instant.</p>
        </td></tr>"""

    title = html.escape(article["title"])
    link = html.escape(article["link"], quote=True)
    meta_parts = [p for p in (article.get("source"), article.get("relative_time")) if p]
    meta = html.escape(", ".join(meta_parts))
    return f"""
        <tr><td style="padding:0 0 22px 0;">
          <p style="margin:0 0 5px 0; font-family:{EMAIL_SANS}; font-size:12px; font-weight:bold; color:{color};">{settings['label']}</p>
          <p style="margin:0 0 5px 0; font-family:{EMAIL_SANS}; font-size:16px; line-height:1.4;">
            <a href="{link}" style="color:{EMAIL_INK}; text-decoration:underline;">{title}</a>
          </p>
          <p style="margin:0; font-family:{EMAIL_SANS}; font-size:13px; color:{EMAIL_MUTED};">{meta}</p>
        </td></tr>"""


def render_email_topic_rows(entry: dict, is_first: bool) -> str:
    topic_title = html.escape(entry["topic"])
    top_pad = "0" if is_first else "28px"
    top_border = "none" if is_first else f"1px solid {EMAIL_RULE}"

    header_row = f"""
        <tr><td style="padding:{top_pad} 0 16px 0; border-top:{top_border};">
          <h2 style="margin:0; font-family:{EMAIL_SERIF}; font-style:italic; font-weight:normal; font-size:21px; color:{EMAIL_INK};">{topic_title}</h2>
        </td></tr>"""

    stories = "".join(render_email_story_row(a, "fr") for a in (entry.get("fr") or [None]))
    stories += "".join(render_email_story_row(a, "en") for a in (entry.get("en") or [None]))
    return header_row + stories


def render_email_html_detailed(digest: list[dict], page_url: str | None) -> str:
    """Gabarit d'e-mail complet (repli utilisé quand aucune page web n'est
    configurée, donc pas de lien "clique ici" possible)."""
    today = dt.date.today().strftime("%d/%m/%Y")
    content_rows = "".join(
        render_email_topic_rows(entry, i == 0) for i, entry in enumerate(digest)
    )

    footer_link = ""
    if page_url:
        safe_url = html.escape(page_url, quote=True)
        footer_link = f'<a href="{safe_url}" style="color:{EMAIL_ACCENT_FR}; text-decoration:underline;">Voir la page complète</a> &nbsp;·&nbsp; '

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>Ta veille du {today}</title>
</head>
<body style="margin:0; padding:0; background:{EMAIL_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{EMAIL_BG};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; width:100%; background:{EMAIL_PAPER};">
          <tr><td style="height:4px; line-height:4px; font-size:0; background:{EMAIL_ACCENT_FR};">&nbsp;</td></tr>
          <tr>
            <td style="padding:36px 32px 8px 32px;">
              <h1 style="margin:0 0 8px 0; font-family:{EMAIL_SERIF}; font-weight:normal; font-size:29px; color:{EMAIL_INK};">Ta veille du {today}</h1>
              <p style="margin:0; font-family:{EMAIL_SANS}; font-size:14px; color:{EMAIL_MUTED};">Un article en français et un en anglais, par thème</p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 4px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {content_rows}
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 32px 32px; border-top:1px solid {EMAIL_RULE};">
              <p style="margin:20px 0 0 0; font-family:{EMAIL_SANS}; font-size:12px; color:{EMAIL_MUTED};">
                {footer_link}Générée automatiquement chaque matin.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def format_plain_text_digest(digest: list[dict], page_url: str | None) -> str:
    """Version texte brut détaillée (repli utilisé quand aucune page web n'est configurée)."""
    today = dt.date.today().strftime("%d/%m/%Y")
    lines = [f"Ta veille du {today}", ""]
    for entry in digest:
        lines.append(entry["topic"])
        lines.append("-" * len(entry["topic"]))
        for lang in ("fr", "en"):
            settings = LANG_SETTINGS[lang]
            articles = entry.get(lang) or []
            if not articles:
                lines.append(f"{settings['label']} : aucun article trouvé.")
                continue
            for article in articles:
                lines.append(f"{settings['label']} : {article['title']} — {article['link']}")
        lines.append("")
    if page_url:
        lines.append(f"Page complète : {page_url}")
    return "\n".join(lines)


def render_email_html_notification(digest: list[dict], page_url: str) -> str:
    """E-mail minimaliste : « ta veille est prête, clique ici » + un bouton.
    Le contenu complet (les articles) vit uniquement sur la page web."""
    today = dt.date.today().strftime("%d/%m/%Y")
    safe_url = html.escape(page_url, quote=True)
    topic_names = html.escape(", ".join(entry["topic"] for entry in digest))
    nb_topics = len(digest)
    theme_word = "thème" if nb_topics <= 1 else "thèmes"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>Ta veille du {today}</title>
</head>
<body style="margin:0; padding:0; background:{EMAIL_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{EMAIL_BG};">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%; background:{EMAIL_PAPER};">
          <tr><td style="height:4px; line-height:4px; font-size:0; background:{EMAIL_ACCENT_FR};">&nbsp;</td></tr>
          <tr>
            <td align="center" style="padding:48px 36px 4px 36px;">
              <p style="margin:0 0 12px 0; font-family:{EMAIL_SANS}; font-size:13px; color:{EMAIL_MUTED};">{today}</p>
              <h1 style="margin:0 0 16px 0; font-family:{EMAIL_SERIF}; font-weight:normal; font-size:27px; color:{EMAIL_INK};">Ta veille est prête</h1>
              <p style="margin:0 0 8px 0; font-family:{EMAIL_SANS}; font-size:15px; line-height:1.6; color:{EMAIL_MUTED};">
                {nb_topics} {theme_word}, chacun avec un article en français et un en anglais.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:28px 36px 40px 36px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:{EMAIL_ACCENT_FR};">
                    <a href="{safe_url}" style="display:inline-block; padding:14px 34px; font-family:{EMAIL_SANS}; font-size:15px; font-weight:600; color:#FFFFFF; text-decoration:none;">Lire ma veille</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 36px 36px 36px; border-top:1px solid {EMAIL_RULE};">
              <p style="margin:20px 0 0 0; font-family:{EMAIL_SANS}; font-size:12px; line-height:1.6; color:{EMAIL_MUTED};">{topic_names}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def format_plain_text_notification(digest: list[dict], page_url: str) -> str:
    today = dt.date.today().strftime("%d/%m/%Y")
    nb_topics = len(digest)
    theme_word = "thème" if nb_topics <= 1 else "thèmes"
    topic_names = ", ".join(entry["topic"] for entry in digest)
    return (
        f"Ta veille du {today} est prête.\n\n"
        f"{nb_topics} {theme_word} : {topic_names}\n\n"
        f"Lire ma veille : {page_url}"
    )


def render_email_html(digest: list[dict], page_url: str | None) -> str:
    """Corps HTML de l'e-mail envoyé. Notification courte + bouton si une page
    web est configurée (PAGE_URL) ; sinon repli avec le contenu complet, faute
    de lien possible vers "clique ici"."""
    if page_url:
        return render_email_html_notification(digest, page_url)
    return render_email_html_detailed(digest, page_url)


def format_plain_text_email(digest: list[dict], page_url: str | None) -> str:
    if page_url:
        return format_plain_text_notification(digest, page_url)
    return format_plain_text_digest(digest, page_url)


# --------------------------------------------------------------------------
# Envoi des notifications
# --------------------------------------------------------------------------

def format_telegram_message(digest: list[dict], page_url: str | None) -> str:
    today = dt.date.today().strftime("%d/%m/%Y")
    lines = [f"<b>🗞 Ta veille du {today}</b>"]

    for entry in digest:
        lines.append(f"\n<b>{html.escape(entry['topic'])}</b>")
        for lang in ("fr", "en"):
            settings = LANG_SETTINGS[lang]
            articles = entry.get(lang) or []
            if not articles:
                lines.append(f"{settings['flag']} Aucun article trouvé.")
                continue
            for article in articles:
                title = html.escape(article["title"])
                link = html.escape(article["link"], quote=True)
                lines.append(f'{settings["flag"]} <a href="{link}">{title}</a>')

    if page_url:
        lines.append(f'\n📄 <a href="{html.escape(page_url, quote=True)}">Voir la page complète</a>')

    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def send_email(
    smtp_user: str,
    smtp_password: str,
    to_addr: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    # Le client mail choisit la dernière partie qu'il sait afficher :
    # texte brut en premier (repli), HTML en dernier (affiché en priorité).
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=REQUEST_TIMEOUT) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_addr], msg.as_string())


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------

def main() -> None:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    digest = build_digest(config)

    html_page = render_html(digest)
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_page)
    print("Page web générée dans docs/index.html")

    page_url = os.environ.get("PAGE_URL", "").strip() or None
    message = format_telegram_message(digest, page_url)

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat_id:
        try:
            send_telegram(tg_token, tg_chat_id, message)
            print("Message Telegram envoyé.")
        except Exception as exc:  # noqa: BLE001
            print(f"! Échec de l'envoi Telegram : {exc}", file=sys.stderr)
    else:
        print("Telegram non configuré (secrets absents) — étape ignorée.")

    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
    email_to = os.environ.get("EMAIL_TO", "").strip()
    if smtp_user and smtp_password and email_to:
        try:
            subject = f"🗞 Ta veille du {dt.date.today().strftime('%d/%m/%Y')}"
            email_html = render_email_html(digest, page_url)
            email_text = format_plain_text_email(digest, page_url)
            send_email(smtp_user, smtp_password, email_to, subject, email_html, email_text)
            print("E-mail envoyé.")
        except Exception as exc:  # noqa: BLE001
            print(f"! Échec de l'envoi e-mail : {exc}", file=sys.stderr)
    else:
        print("E-mail non configuré (secrets absents) — étape ignorée.")

    if not (tg_token and tg_chat_id) and not (smtp_user and smtp_password and email_to):
        print(
            "\nAucun canal de notification n'est configuré : seule la page web a été "
            "générée. Configure Telegram et/ou l'e-mail (voir README.md) pour "
            "recevoir la veille automatiquement.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

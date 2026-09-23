# 🗞 Veille quotidienne — actus FR + EN sur tes thèmes, chaque jour, gratuit

Ce mini-projet t'envoie **chaque jour, à heure fixe**, un article en **français**
et un article en **anglais** pour chacun des thèmes que tu choisis. Tu reçois
le résultat :
- en **message Telegram** (notification instantanée sur ton téléphone), et/ou
- par **e-mail**, et
- toujours sur une **page web** qui se met à jour toute seule (gratuite, via
  GitHub Pages), avec le lien envoyé dans la notification.

Tout tourne gratuitement sur **GitHub Actions** (le "cron" qui déclenche le
script chaque jour) — pas de serveur à payer, pas de PC à laisser allumé.

## Comment ça marche, en résumé

```
GitHub Actions (réveil quotidien à l'heure que tu choisis)
        │
        ▼
  digest.py  ── va chercher, pour chaque thème de config.yaml,
        │        le meilleur article FR + le meilleur article EN
        │        (flux RSS gratuits de Google Actualités, sans clé API)
        │
        ├──▶ génère docs/index.html  ──▶ publié sur GitHub Pages
        │
        └──▶ envoie la notification ──▶ Telegram et/ou e-mail
```

La page web (`docs/index.html`) est stylée avec **Tailwind CSS**, chargé
depuis son CDN (`cdn.tailwindcss.com`) directement dans la page : aucune
étape de build, ça fonctionne tel quel une fois déployé sur GitHub Pages —
il faut juste que la personne qui consulte la page ait une connexion
Internet (normal pour visiter une page web).

Aucune de ces briques ne coûte quoi que ce soit : GitHub Actions est gratuit
pour ce genre d'usage (quelques dizaines de minutes par mois), les flux RSS de
Google Actualités ne demandent pas de clé, l'API Telegram est gratuite, et
GitHub Pages aussi.

---

## Étape 1 — Mettre le projet sur GitHub

1. Crée un compte GitHub si tu n'en as pas (gratuit) : https://github.com/signup
2. Crée un nouveau dépôt, par exemple nommé `veille-quotidienne` (peut être
   privé ou public, les deux fonctionnent).
3. Dézippe le fichier que je t'ai donné, puis mets tous les fichiers dedans
   dans ce dépôt (soit en les glissant sur la page GitHub du dépôt, soit avec
   `git add / commit / push` si tu es à l'aise avec Git).

À la fin, ton dépôt doit contenir :
```
config.yaml
digest.py
requirements.txt
README.md
docs/index.html
.github/workflows/daily-digest.yml
```

## Étape 2 — Choisir tes thèmes

Ouvre `config.yaml` et modifie la liste `topics` avec ce qui t'intéresse,
par exemple :

```yaml
topics:
  - "Intelligence artificielle"
  - "Formule 1"
  - "Climat"
```

Tu peux en mettre autant que tu veux (garde en tête que plus il y en a, plus
le script met de temps à s'exécuter — quelques secondes par thème).

## Étape 3 — Choisir ton (tes) canal(ux) de réception

### Option A — E-mail via Gmail (canal principal recommandé)

L'e-mail est volontairement court : « Ta veille est prête » + un bouton
« Lire ma veille » qui pointe vers la page web (le contenu détaillé vit sur
la page, pas dans l'e-mail). Il a son propre gabarit visuel — cohérent avec
la page (même palette), mais écrit spécialement pour bien s'afficher dans
une boîte mail : polices "web-safe", mise en page en tableaux, pas de
dépendance à des polices externes.

*Si tu n'as pas configuré `PAGE_URL` (page GitHub Pages), le script bascule
automatiquement sur un e-mail détaillé contenant tous les articles, puisqu'il
n'y a alors pas de lien vers lequel pointer le bouton.*

1. Active la validation en deux étapes sur ton compte Gmail (nécessaire pour
   l'étape suivante) : https://myaccount.google.com/security
2. Crée un **mot de passe d'application** :
   https://myaccount.google.com/apppasswords → choisis "Autre", nomme-le
   "veille", copie le mot de passe généré (16 caractères).
3. Note :
   - `SMTP_USER` = ton adresse Gmail complète
   - `SMTP_PASSWORD` = le mot de passe d'application (pas ton vrai mot de
     passe Gmail)
   - `EMAIL_TO` = l'adresse où tu veux recevoir la veille (peut être la même)

Tu peux bien sûr utiliser un autre fournisseur SMTP que Gmail : modifie alors
`smtp.gmail.com` dans `digest.py` (fonction `send_email`) en conséquence.

### Option B — Telegram (en plus, optionnel)

Rien n'empêche de cumuler : Telegram est gratuit, instantané sur le
téléphone, et prend 2 minutes à configurer si tu veux une notification
push en plus de l'e-mail.

1. Ouvre Telegram, cherche **@BotFather**, envoie-lui `/newbot` et suis les
   instructions (choisis un nom et un identifiant se terminant par `bot`).
2. BotFather te donne un **token** qui ressemble à
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` → note-le, c'est ton
   `TELEGRAM_BOT_TOKEN`.
3. Envoie n'importe quel message à ton bot (cherche-le par le nom que tu lui
   as donné et clique sur "Démarrer").
4. Récupère ton **chat_id** : ouvre dans ton navigateur
   `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` (remplace
   `<TON_TOKEN>` par ton vrai token) juste après lui avoir envoyé un message.
   Tu verras un champ `"chat":{"id": 123456789, ...}` → ce nombre est ton
   `TELEGRAM_CHAT_ID`.

*(Une piste WhatsApp a été évoquée mais écartée : côté officiel, Meta impose
une vérification "Business", un numéro dédié et des messages-modèles
pré-validés — donc plus vraiment gratuit ni immédiat ; côté non-officiel,
ça reviendrait à automatiser ton compte perso en violation des conditions
d'utilisation de WhatsApp, avec un risque de blocage du numéro. Email +
Telegram couvrent le besoin sans ces inconvénients.)*

## Étape 4 — Ajouter tes identifiants dans GitHub (secrets)

Dans ton dépôt : **Settings → Secrets and variables → Actions → New
repository secret**, ajoute ceux qui te concernent :

| Nom               | Valeur                                   |
|-------------------|-------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | le token donné par BotFather            |
| `TELEGRAM_CHAT_ID`   | ton chat_id                             |
| `SMTP_USER`          | ton adresse Gmail                       |
| `SMTP_PASSWORD`      | le mot de passe d'application           |
| `EMAIL_TO`           | l'adresse de destination                |

Ce sont des secrets : personne (même toi une fois enregistrés) ne peut les
relire depuis l'interface GitHub, ils sont seulement utilisables par le
workflow.

## Étape 5 — Activer la page web (GitHub Pages)

1. **Settings → Pages**.
2. **Source** : "Deploy from a branch".
3. **Branch** : `main`, dossier `/docs` → **Save**.
4. GitHub affiche l'URL de ta page (quelque chose comme
   `https://ton-pseudo.github.io/veille-quotidienne/`). Attends 1-2 minutes
   après le premier passage du script pour qu'elle soit en ligne.
5. (Optionnel mais recommandé) Ajoute cette URL comme **variable** pour
   qu'elle apparaisse dans tes notifications : **Settings → Secrets and
   variables → Actions → onglet "Variables" → New repository variable** :
   - Nom : `PAGE_URL`
   - Valeur : l'URL de ta page (celle de l'étape 4)

## Étape 6 — Régler l'heure d'envoi

Ouvre `.github/workflows/daily-digest.yml` et modifie la ligne :

```yaml
- cron: "0 6 * * *"
```

Le format est `minute heure * * *`, **en heure UTC** (pas l'heure de Paris !).
Par exemple pour recevoir ta veille à 8h00 heure de Paris :
- en été (heure d'été, UTC+2) → `0 6 * * *`
- en hiver (heure d'hiver, UTC+1) → `0 7 * * *`

⚠️ GitHub Actions ne s'ajuste pas tout seul au changement d'heure : le
décalage se fera d'une heure deux fois par an, à toi de retoucher ce fichier
si ça t'ennuie (ou d'accepter le petit décalage saisonnier). Un outil pratique
pour construire ton expression cron : https://crontab.guru
Note aussi que GitHub peut retarder un déclenchement programmé de quelques
minutes en cas de forte charge sur leurs serveurs — c'est rare mais possible,
et sans solution gratuite garantissant la seconde près.

## Étape 7 — Tester tout de suite

Pas besoin d'attendre le lendemain :
1. Onglet **Actions** de ton dépôt.
2. Clique sur **"Veille quotidienne"** dans la liste à gauche.
3. Bouton **"Run workflow"** → **"Run workflow"**.
4. Après ~30 secondes à 1 minute, tu dois recevoir ta notification et voir la
   page se mettre à jour.

Si rien ne se passe, ouvre le détail de l'exécution dans l'onglet Actions :
les messages `print(...)` du script (en français) t'indiquent précisément ce
qui a été essayé et ce qui a échoué.

---

## Limites connues (honnêteté avant tout)

- **Google Actualités (RSS)** est gratuit et ne demande pas de clé, mais ce
  n'est pas une API officiellement garantie par Google : le format peut
  changer un jour. Si le script s'arrête de fonctionner, une alternative est
  de passer par une vraie API comme [NewsAPI.org](https://newsapi.org)
  (gratuite jusqu'à 100 requêtes/jour, nécessite une clé).
- Le script prend le **premier résultat** retourné par Google Actualités pour
  chaque thème/langue, c'est-à-dire l'article jugé le plus pertinent par leur
  algorithme sur la fenêtre de temps choisie (`lookback_days`) — ce n'est pas
  forcément "l'actu la plus importante" au sens éditorial.
- L'heure d'envoi via GitHub Actions est fiable à quelques minutes près, pas
  à la seconde.

## Pour aller plus loin (idées, non implémentées)

- Ajouter un résumé en une phrase de chaque article (par exemple en appelant
  l'API Claude dans `digest.py` avec ta propre clé API).
- Passer `articles_per_topic` à 2 ou 3 dans `config.yaml` pour avoir plus de
  choix par thème et par langue.
- Ajouter un canal Slack ou Discord (même principe qu'avec Telegram : une
  requête HTTP vers un webhook).

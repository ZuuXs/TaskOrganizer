# 🗓️ Planificateur Intelligent de Tâches

Application Streamlit qui planifie automatiquement vos tâches en tenant compte de votre Google Calendar, vos contraintes personnelles et une IA (Perplexity) pour extraire et optimiser votre planning.

---

## ✨ Fonctionnalités

- **Extraction IA** : Décrivez vos tâches en langage naturel → Perplexity extrait titre, durée, deadline et priorité
- **Intégration Google Calendar** : Importe vos événements existants automatiquement
- **Algorithme Greedy** : Planifie les tâches intelligemment en respectant vos contraintes
- **Contraintes personnalisables** : Max heures/jour, pas après 22h, pas le dimanche, pause repas
- **Vue calendrier** : Navigation par semaine avec code couleur (rouge = occupé, bleu = tâches)
- **Export Google Calendar** : Ajoute les créneaux planifiés directement dans votre agenda
- **Conseils IA** : Perplexity vous donne des conseils de productivité sur votre planning

---

## 🚀 Installation

### 1. Cloner le projet

```bash
git clone <url-du-repo>
cd TaskOrganizer
```

### 2. Créer un environnement virtuel

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

```bash
# Copier le fichier exemple
cp .env.example .env

# Éditer .env avec vos clés
```

---

## 🔑 Configuration des APIs

### API Perplexity

1. Créez un compte sur [Perplexity AI](https://www.perplexity.ai/)
2. Accédez à [Settings → API](https://www.perplexity.ai/settings/api)
3. Cliquez sur **"Generate"** pour créer une clé API
4. Copiez la clé dans votre `.env` :
   ```
   PERPLEXITY_API_KEY=pplx-xxxxxxxxxxxx
   ```
   > Ou entrez-la directement dans la barre latérale de l'application

### Google Calendar API

#### Étape 1 : Créer un projet Google Cloud

1. Allez sur [Google Cloud Console](https://console.cloud.google.com/)
2. Cliquez sur **"Nouveau projet"** → donnez-lui un nom (ex: `PlanificateurTaches`)
3. Sélectionnez votre nouveau projet

#### Étape 2 : Activer l'API Google Calendar

1. Dans le menu → **"APIs & Services"** → **"Bibliothèque"**
2. Recherchez **"Google Calendar API"**
3. Cliquez sur **"Activer"**

#### Étape 3 : Créer des identifiants OAuth 2.0

1. Menu → **"APIs & Services"** → **"Identifiants"**
2. Cliquez sur **"+ Créer des identifiants"** → **"ID client OAuth 2.0"**
3. Si demandé, configurez l'**Écran de consentement OAuth** :
   - Type d'utilisateur : **Externe**
   - Nom de l'application : ce que vous voulez
   - Email de support : votre email
   - Sauvegardez
4. Retournez créer l'ID client :
   - Type d'application : **Application de bureau**
   - Nom : `PlanificateurTaches`
   - Cliquez **"Créer"**
5. Téléchargez le fichier JSON en cliquant sur **⬇️**
6. **Renommez-le `credentials.json`** et placez-le dans le dossier du projet

#### Étape 4 : Ajouter votre compte comme utilisateur test

1. Menu → **"APIs & Services"** → **"Écran de consentement OAuth"**
2. Section **"Utilisateurs test"** → **"+ Add Users"**
3. Ajoutez l'adresse email de votre compte Google Calendar

#### Étape 5 : Première connexion

Lors du premier clic sur "Connecter Google Calendar" dans l'app :
- Un navigateur s'ouvre automatiquement
- Connectez-vous avec votre compte Google
- Autorisez l'accès au calendrier
- Le fichier `token.json` est créé automatiquement (les fois suivantes, pas besoin de se ré-authentifier)

---

## ▶️ Lancer l'application

```bash
streamlit run app.py
```

L'application s'ouvre automatiquement sur [http://localhost:8501](http://localhost:8501)

---

## 🗂️ Structure du projet

```
TaskOrganizer/
├── app.py                 # Application Streamlit principale
├── google_calendar.py     # Intégration Google Calendar (OAuth2 + CRUD)
├── perplexity_api.py      # Intégration API Perplexity
├── scheduler.py           # Algorithme de planification greedy
├── requirements.txt       # Dépendances Python
├── .env.example           # Template variables d'environnement
├── .env                   # Vos clés API (à créer, ne pas committer)
├── credentials.json       # Identifiants Google OAuth (à ne pas committer)
└── token.json             # Token Google (généré automatiquement)
```

---

## 🎨 Guide d'utilisation

### Onglet 1 — 📝 Tâches

1. **Saisir un prompt** : Décrivez vos tâches en langage naturel
   - Exemple : *"Je dois finir mon rapport de stage pour vendredi, réviser pour l'exam de maths lundi prochain (3h, haute priorité), et lire 2 chapitres de mon livre cette semaine"*
2. Cliquer **"Extraire les tâches avec l'IA"** → l'IA remplit titre, durée, deadline, priorité
3. **Éditer** les tâches extraites si besoin (cliquez sur une tâche pour l'ouvrir)
4. **Ajouter manuellement** des tâches supplémentaires

### Onglet 2 — 📅 Créneaux Occupés

1. **Connecter Google Calendar** → importe vos événements des 30 prochains jours
2. **Ajouter manuellement** des créneaux (cours, travail, rendez-vous...)

### Onglet 3 — 🗓️ Planification

1. Ajustez les **contraintes** dans la barre latérale gauche
2. Cliquer **"Générer le Planning"**
3. Naviguez dans le calendrier semaine par semaine
4. Consultez les messages explicatifs et les tâches impossibles
5. Optionnel : cliquer **"Conseils IA"** pour des recommandations Perplexity

### Onglet 4 — ✅ Exporter

1. Sélectionnez les créneaux à exporter
2. Cliquer **"Exporter vers Google Calendar"**
3. Téléchargez le résumé en `.txt` si besoin

---

## ⚙️ Algorithme de planification

L'algorithme greedy fonctionne en 3 étapes :

1. **Tri des tâches** : deadline proche → priorité haute → durée courte
2. **Génération des créneaux libres** : pour chaque jour sur 30 jours en soustrayant :
   - Créneaux occupés (Google Calendar + manuels)
   - Pause repas (12h-13h si activée)
   - Heures hors plage de travail
   - Dimanche (si désactivé)
3. **Attribution greedy** : pour chaque tâche, on remplit les créneaux libres jour par jour
   - Une tâche peut être scindée sur plusieurs jours
   - Si impossible avant la deadline → marquée "NON PLANIFIABLE"

---

## ❓ Problèmes courants

| Problème | Solution |
|----------|----------|
| `credentials.json introuvable` | Vérifiez que le fichier est bien dans le dossier du projet |
| Navigateur ne s'ouvre pas | Lancez manuellement l'URL affichée dans le terminal |
| Erreur `401 Perplexity` | Vérifiez votre clé API dans `.env` ou la barre latérale |
| Tâches toutes "NON PLANIFIABLES" | Augmentez le max heures/jour ou repoussez les deadlines |
| `token.json` expire | Supprimez `token.json` et reconnectez-vous |

---

## 🔒 Sécurité

- Ne commitez **jamais** `credentials.json`, `token.json`, ou `.env` dans git
- Ajoutez ces fichiers à `.gitignore` :
  ```
  credentials.json
  token.json
  .env
  ```

---

## 📄 Licence

MIT — libre d'utilisation et de modification.

# 📅 Planificateur Intelligent de Tâches

Une application Streamlit pour planifier intelligemment vos tâches en tenant compte de vos contraintes et créneaux occupés, avec intégration Google Calendar.

## 🚀 Fonctionnalités

- **Gestion des tâches** : Ajoutez des tâches avec titre, durée, deadline et priorité
- **Créneaux occupés** : Importation depuis Google Calendar ou saisie manuelle
- **Contraintes personnalisables** : Heures max/jour, heure limite, pas de dimanche, pause déjeuner
- **Algorithme intelligent** : Planification greedy avec tri par deadline, priorité et durée
- **Intégration Google Calendar** : Import/export des créneaux et tâches planifiées
- **Interface intuitive** : Visualisation claire du planning par jour

## 📦 Installation

### Prérequis
- Python 3.7+
- pip

### Étapes

1. Clonez le dépôt:
```bash
git clone https://github.com/votre-repo/TaskOrganizer.git
cd TaskOrganizer
```

2. Installez les dépendances:
```bash
pip install -r requirements.txt
```

3. Pour l'intégration Google Calendar:
```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## 🔑 Configuration Google Calendar

1. **Créez un projet Google Cloud** :
   - Allez sur [Google Cloud Console](https://console.cloud.google.com/)
   - Créez un nouveau projet
   - Activez les API "Google Calendar API"

2. **Créez des identifiants OAuth** :
   - Allez dans "APIs & Services" > "Credentials"
   - Cliquez sur "Create Credentials" > "OAuth client ID"
   - Sélectionnez "Desktop app"
   - Téléchargez le fichier JSON et renommez-le `credentials.json`
   - Placez-le dans le dossier du projet

3. **Modifiez le fichier** `credentials.json` avec vos identifiants réels

## 🎯 Utilisation

### Lancement de l'application
```bash
streamlit run main.py
```

### Interface utilisateur

1. **📝 Tâches** : Ajoutez et gérez vos tâches
2. **🕒 Créneaux Occupés** : Ajoutez manuellement ou importez depuis Google Calendar
3. **⚙️ Contraintes** : Configurez vos préférences de planification
4. **📅 Planification** : Lancez l'algorithme et visualisez votre planning
5. **🔄 Google Calendar** : Connectez-vous et synchronisez avec votre calendrier

### Exemple de workflow

1. Ajoutez 3-5 tâches avec différentes priorités et deadlines
2. Ajoutez quelques créneaux occupés (ou importez depuis Google Calendar)
3. Configurez vos contraintes
4. Lancez la planification
5. Exportez le résultat vers Google Calendar

## 📂 Structure du projet

```
TaskOrganizer/
├── main.py                  # Application principale Streamlit
├── google_calendar.py       # Intégration Google Calendar
├── requirements.txt         # Dépendances Python
├── credentials.json         # Fichier de configuration Google API
└── README.md                # Documentation
```

## 🔧 Développement

### Tests
L'application peut être testée localement avec des données fictives sans authentification Google Calendar.

### Améliorations possibles
- Amélioration de l'algorithme de planification (backtracking, optimisation)
- Support multi-calendrier
- Notifications et rappels
- Synchronisation automatique
- Interface mobile responsive

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

## 📄 Licence

MIT License - voir le fichier LICENSE pour plus de détails.

---

*Made with ❤️ and Streamlit* 🎈
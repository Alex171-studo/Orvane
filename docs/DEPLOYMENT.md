# Déployer ORVANE sur Streamlit Community Cloud

## Préparer la version

Exécuter l’installation locale et les trois contrôles Ruff/Pytest du README avec Python 3.12. Lancer également `python scripts/smoke_test.py`. Vérifier que `.env`, `.venv` et `.streamlit/secrets.toml` sont ignorés. Utiliser le dépôt Git local à la racine de `orvane`.

Pour publier sur un dépôt GitHub vide autorisé, remplacer l’adresse du dépôt par la vôtre :

```bash
git status --short
git log -1 --oneline
git remote add origin https://github.com/ORGANISATION/orvane.git
git push -u origin main
```

## Configurer la plateforme

1. Connecter le compte GitHub à Streamlit Community Cloud, puis choisir **Create app**.
2. Sélectionner le dépôt, la branche `main` et `app.py`. Si ORVANE fait partie d’un dépôt plus grand, adapter le chemin au point d’entrée et vérifier la découverte des dépendances et de la configuration Streamlit.
3. Dans **Advanced settings**, sélectionner Python 3.12. Utiliser les paramètres de secrets ci-dessous si le mode connecté est souhaité.
4. Déployer. Ouvrir l’URL fournie et vérifier l’accueil puis le parcours complet. Sans clé, vérifier que **Nouveau compte rendu** propose **Texte**, **Microphone** et **Fichier audio**, puis enregistrer une note personnelle. Les exemples préenregistrés sont une quatrième option sur les chantiers fictifs. [Procédure officielle Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

## Configurer Groq et OpenAI

Créer une clé dans le projet Groq destiné à ORVANE. Vérifier que le compte autorise Whisper Large V3 Turbo ou Whisper Large V3 et l’envoi direct des formats requis. [Clés Groq](https://console.groq.com/keys) · [Speech to Text](https://console.groq.com/docs/speech-to-text)

Créer une clé de projet OpenAI. Vérifier le budget, les droits sur la Responses API et l’accès aux modèles utilisés. Le compte peut nécessiter une configuration de facturation. [Clés OpenAI](https://platform.openai.com/api-keys) · [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) · [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4)

Dans le gestionnaire de secrets Streamlit, reprendre les noms de `.streamlit/secrets.toml.example`. Définir `APP_MODE = "live"`, puis renseigner `APP_ACCESS_TOKEN`, `GROQ_API_KEY` et `OPENAI_API_KEY` avec leurs valeurs privées. Les autres variables du fichier .env.example sont acceptées sous forme de clés TOML de premier niveau. Redémarrer et vérifier l’écran d’invitation.

## Recette de production

- Dans une fenêtre privée, ouvrir le site et vérifier l’accès par invitation. Autoriser le microphone sur la page HTTPS après interaction avec le navigateur.
- Créer un chantier et enregistrer une courte note sans donnée sensible. Contrôler la transcription, la langue, le délai de réponse et le relevé d’usage Groq. Répéter avec un fichier importé.
- Corriger une phrase puis autoriser l’analyse. Vérifier les citations, le modèle effectivement servi et les compteurs. Naviguer entre les pages et vérifier que le nombre de requêtes reste stable.
- Modifier un responsable, laisser une date inconnue, valider et télécharger le PDF sur ordinateur et téléphone. Vérifier le plan d’action, les KPI, le versionnage et le rechargement d’une archive dans une session neuve.
- Comparer les deux modèles uniquement si le budget a été explicitement alloué. Pour les erreurs fournisseur, contrôler que le texte reste présent et que l’utilisateur peut réessayer.

La mémoire et le temps de calcul de Community Cloud sont limités. L’application peut se mettre en veille ou redémarrer. Un onglet, un appareil ou une nouvelle connexion peut créer une autre session. Les archives locales sont le moyen de sauvegarde du MVP. La livraison prépare le déploiement et ne fournit aucune URL de production.

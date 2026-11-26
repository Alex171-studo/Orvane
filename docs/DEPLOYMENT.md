# Déploiement Streamlit Community Cloud

Le dépôt utilise Python 3.12 et `app.py` comme point d’entrée. Exécuter Ruff, Pytest et le contrôle de démarrage indiqués dans le README, puis publier le commit testé sur la branche GitHub suivie par l’application.

Dans Community Cloud, sélectionner le dépôt, la branche et `app.py`, puis Python 3.12 dans les paramètres avancés. Pour une application existante, vérifier la branche suivie et modifier ses secrets depuis ses paramètres. [Guide Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

Créer une clé Groq pour la transcription Whisper et une clé de projet OpenAI disposant du modèle d’analyse. Renseigner les valeurs privées sous les noms ci-dessous dans les secrets Streamlit. [Clés Groq](https://console.groq.com/keys) · [Clés OpenAI](https://platform.openai.com/api-keys)

```toml
GROQ_API_KEY = "votre clé Groq"
OPENAI_API_KEY = "votre clé OpenAI"
```

La transcription utilise par défaut `whisper-large-v3-turbo` et l’analyse utilise `gpt-5.4-mini`. Les deux clés sont indépendantes. Les anciens paramètres `APP_MODE` et `APP_ACCESS_TOKEN` peuvent être supprimés. Le fichier `.env.example` contient les limites configurables. Le navigateur utilise le microphone après autorisation sur HTTPS.

## Vérification en ligne

Ouvrir l’application dans une nouvelle session. L’accueil doit présenter un chantier et une note vides. Avec un compte fournisseur autorisé pour ce test, transcrire un court vocal, corriger le texte, générer un rapport, modifier une action et valider le PDF. Vérifier aussi le chargement d’un fichier audio depuis un téléphone.

Sur un site public, chaque visiteur peut déclencher des appels facturables. Le quota par session repart de zéro à la création d’une nouvelle session. Configurer la facturation et les alertes des comptes fournisseurs en conséquence. La mise en veille, l’interruption de la connexion ou le redémarrage peuvent effacer les données en mémoire.

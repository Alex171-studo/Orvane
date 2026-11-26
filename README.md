# ORVANE

Du terrain à la décision. ORVANE transforme les notes d’une visite de chantier en compte rendu et en plan d’action. Chaque session s’ouvre sur une note vierge.

## Utiliser l’application

1. Renseigner le chantier et la date de visite, puis écrire la note, enregistrer un vocal ou importer un fichier audio.
2. Pour un vocal, cliquer sur **Transcrire le vocal** et corriger le texte obtenu. Pour garder une note sans lancer l’analyse, choisir **Enregistrer la note**.
3. Cliquer sur **Confirmer et générer le compte rendu**. Relire la synthèse, le plan d’action, les observations, les problèmes, les décisions et les points à clarifier. Chaque élément renvoie à un passage de la note.
4. Corriger les valeurs directement dans les tableaux. Une date, une priorité ou un responsable inconnu peut rester vide. Cliquer sur **Valider le compte rendu**, puis télécharger le PDF. Une correction ultérieure ouvre une nouvelle version à valider.

Les notes de la session sont accessibles dans le volet latéral. La sauvegarde JSON permet de les retrouver après un redémarrage. Les enregistrements audio restent en mémoire et sont exclus de l’archive.

## Installer et démarrer

À la racine du dépôt, avec Python 3.12 :

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
streamlit run app.py
```

En local, renseigner les clés dans `.env`. Sur Streamlit Community Cloud, utiliser les secrets de l’application. `GROQ_API_KEY` active la transcription et `OPENAI_API_KEY` active la génération du rapport. Les clés restent sur le serveur. L’ancien mode de démonstration et le code d’invitation sont ignorés. Sans clé, la saisie et la sauvegarde JSON restent disponibles.

## Vérifier le projet

```bash
ruff check .
pytest -q
pytest --cov=src --cov-report=term-missing --cov-fail-under=85
python scripts/smoke_test.py
python scripts/evaluate.py
```

Ces commandes fonctionnent hors ligne vis-à-vis des fournisseurs. Les clients SDK sont vérifiés avec des transports simulés. Le corpus annoté est réservé à l’évaluation.

## Organisation

| Chemin | Contenu |
|---|---|
| `app.py`, `src/ui/` | Saisie, transcription, revue et téléchargement Streamlit |
| `src/domain/`, `src/storage/` | Modèles Pydantic et données privées de session |
| `src/providers/`, `src/prompts/` | Groq Whisper, OpenAI Responses API et prompts versionnés |
| `src/services/` | Calendrier, contrôles métier, versions, PDF, statistiques et évaluation |
| `data/evaluation/`, `tests/` | Cas annotés et tests automatisés |
| `.streamlit/`, `.github/workflows/` | Configuration Cloud et vérifications CI |

Voir les [instructions de déploiement](docs/DEPLOYMENT.md), les [limites de sécurité](docs/SECURITY.md) et la [méthode d’évaluation](docs/EVALUATION.md).

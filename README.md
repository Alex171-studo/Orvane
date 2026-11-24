# ORVANE

**Du terrain à la décision.** Un conducteur de travaux peut dicter sa visite, corriger le texte, contrôler les propositions et publier un compte rendu accompagné d’un plan d’action. L’interface et les rapports sont en français.

## Démarrage local

Depuis le répertoire `orvane`, avec Python 3.12 et son module venv disponibles :

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
streamlit run app.py
```

Ouvrir l’adresse locale affichée par Streamlit. Pour utiliser uniquement l’application, installer `requirements.txt`. Le mode initial fonctionne sans clé.

## Ajouter une note ou un vocal

Dans **Nouveau compte rendu**, choisissez un chantier ou utilisez **Ajouter un chantier**. **Texte** est sélectionné par défaut. Saisissez votre note puis cliquez sur **Enregistrer la note**. Pour un vocal, choisissez **Microphone** ou **Fichier audio**, enregistrez ou importez le son, puis cliquez sur **Enregistrer le vocal**. Retrouvez la note dans **Dossier de travail**.

Ces entrées fonctionnent aussi sans clés. Un vocal enregistré peut être réécouté dans la session et transcrit manuellement. Le texte est inclus dans l’archive JSON. Le son reste temporaire et se perd si la session est fermée, réinitialisée ou remplacée par une archive. Le mode connecté permet d’envoyer le son à Groq, puis le texte approuvé à OpenAI par deux actions distinctes.

## Essayer un compte rendu préenregistré

1. Dans **Nouveau compte rendu**, choisir l’un des cinq chantiers fictifs, sélectionner **Note préenregistrée** et ouvrir la note d’exemple.
2. Lire le texte et confirmer la transcription. Charger la proposition associée au chantier. La démo reconnaît la note fournie, à la normalisation des espaces et des caractères près. L’analyse d’un texte libre requiert le mode connecté.
3. Comparer les citations à la note. Corriger la synthèse et les tableaux. Pour ajouter une action, compléter une nouvelle ligne dans l’onglet Actions avec sa description, son statut et une citation exacte. Enregistrer ou valider explicitement.
4. Télécharger le PDF ou le JSON. Le plan d’action et les indicateurs reprennent la dernière révision validée de chaque note. Une modification du suivi ouvre un brouillon à valider.
5. Exporter **Données de session → Exporter la session** avant de quitter. L’archive contient les projets, notes, rapports, révisions, événements et mesures. Le téléchargement individuel d’un rapport sert à l’exploitation de ce rapport. Pour restaurer la session, utiliser l’archive complète.

## Mode connecté

Copier `.env.example` dans `.env`. Définir `APP_MODE=live`, un `APP_ACCESS_TOKEN` aléatoire d’au moins 24 caractères, et les clés des services utilisés. Un code d’invitation peut être généré avec `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Le saisir dans l’écran d’accès. Si le site conserve le mode démo, un utilisateur peut ouvrir « Transcrire le vocal · Accès sur invitation » sur sa propre note et saisir ce même code. Le bouton « Transcrire le vocal » envoie ensuite le son à Groq. Le même principe s’applique à l’analyse OpenAI. Les exemples préenregistrés restent hors ligne. Sur Community Cloud, utiliser les secrets de l’application.

| Paramètre | Défaut | Effet |
|---|---|---|
| GROQ_API_KEY | vide | Authentifie la transcription audio |
| GROQ_TRANSCRIPTION_MODEL | whisper-large-v3-turbo | Alternative disponible : whisper-large-v3 |
| TRANSCRIPTION_LANGUAGE | fr | Code de langue sur deux lettres |
| OPENAI_API_KEY | vide | Authentifie l’analyse du texte |
| OPENAI_MODEL / OPENAI_EVAL_MODEL | gpt-5.4-mini / gpt-5.4 | Modèle d’extraction et modèle de comparaison |
| APP_TIMEZONE | Europe/Paris | Fuseau attribué aux nouveaux chantiers |
| MAX_AUDIO_SIZE_MB | 20 | Mo décimaux, plafond de 25 Mo en envoi direct |
| MAX_TRANSCRIPT_CHARS | 30000 | Taille maximale de la note |
| MAX_EXTRACTION_OUTPUT_TOKENS | 4096 | Budget de sortie par extraction |
| MAX_API_CALLS_PER_SESSION | 10 | Tentatives Groq et OpenAI cumulées |
| MAX_ATTEMPTS | 1 | Jusqu’à trois tentatives sur rejet HTTP 429 |
| GROQ_REQUEST_TIMEOUT_SECONDS / OPENAI_REQUEST_TIMEOUT_SECONDS | 60 / 60 | Délais réseau des SDK |
| PROMPT_VERSION | v2 | Variante v1 également disponible |

Avec une clé OpenAI seule, le parcours texte est disponible. Pour l’audio, autoriser le microphone dans le navigateur ou importer un WAV, MP3, M4A, OGG ou WebM. Confirmer l’envoi à Groq, relire le résultat, puis autoriser séparément son analyse par OpenAI. Chaque service peut facturer ses propres opérations.

## Vérifications

```bash
ruff check .
pytest -q
pytest --cov=src --cov-report=term-missing
python scripts/smoke_test.py
python scripts/evaluate.py
python scripts/evaluate.py --demo --output evaluation-results-demo.json
```

La suite utilise les vrais SDK avec un transport HTTP simulé et les outils de test de Streamlit. Le smoke test démarre et arrête un serveur local. La dernière commande évalue les cinq fixtures sur leurs annotations et affiche le tableau des résultats. Les performances de GPT-5.4 mini et GPT-5.4 nécessitent une campagne explicitement autorisée.

### Recette locale du 23 novembre 2026

Python 3.12.3, Ruff sans anomalie, **98 tests réussis**, couverture de **95 % sur src**, branches actives. Les adaptateurs Groq et OpenAI atteignent respectivement 86 % et 90 %, la validation métier 98 %, le workflow 92 % et le repository de session 98 %.

Le serveur a répondu sur son endpoint de santé et sa page d’accueil. Le tableau de bord a été rendu dans Chromium en 1440 × 900 et 390 × 844. Un microphone synthétique a permis de vérifier la capture, l’arrêt et la réception en mémoire avant envoi. La transcription et l’analyse ont été exercées avec les SDK installés et des transports simulés. La recette avec de vraies clés et la publication Cloud restent à réaliser.

## Organisation du dépôt

```text
orvane/
├── .github/
│   └── workflows/
│       └── ci.yml
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── data/
│   ├── demo/
│   │   └── sites.json
│   └── evaluation/
│       ├── cases.json
│       ├── demo_targets.json
│       ├── expected_outputs.json
│       └── replay_report.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── EVALUATION.md
│   ├── PROMPT_ENGINEERING.md
│   └── SECURITY.md
├── scripts/
│   ├── __init__.py
│   ├── compare_models.py
│   ├── evaluate.py
│   └── smoke_test.py
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── errors.py
│   │   └── models.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── extraction_v1.py
│   │   ├── extraction_v2.py
│   │   └── registry.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── demo_provider.py
│   │   ├── groq_transcription.py
│   │   ├── openai_extraction.py
│   │   └── runtime.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── analytics_service.py
│   │   ├── audio_service.py
│   │   ├── evaluation_service.py
│   │   ├── extraction_service.py
│   │   ├── reporting_service.py
│   │   ├── validation_service.py
│   │   └── workflow_service.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session_repository.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── editors.py
│   │   ├── pages.py
│   │   └── styles.py
│   └── __init__.py
├── tests/
│   ├── integration/
│   │   ├── test_providers.py
│   │   ├── test_reports.py
│   │   └── test_workflow.py
│   ├── security/
│   │   └── test_boundaries.py
│   ├── ui/
│   │   └── test_application.py
│   ├── unit/
│   │   ├── test_domain.py
│   │   └── test_validation.py
│   ├── conftest.py
│   └── test_prompt_regression.py
├── .env.example
├── .gitignore
├── AGENTS.md
├── README.md
├── app.py
├── pyproject.toml
├── requirements-dev.txt
└── requirements.txt
```

Les procédures détaillées sont dans [Architecture](docs/ARCHITECTURE.md), [Prompts](docs/PROMPT_ENGINEERING.md), [Évaluation](docs/EVALUATION.md), [Sécurité](docs/SECURITY.md) et [Déploiement](docs/DEPLOYMENT.md).

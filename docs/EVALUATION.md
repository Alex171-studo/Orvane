# Évaluer la qualité

Le corpus principal contient 21 notes en français. Chaque cas possède un identifiant, un chantier, une date de référence avec décalage et une annotation explicite. Les attentes ont été écrites pour les scénarios, indépendamment d’une sortie fournisseur. Une contre-annotation par des conducteurs de travaux reste à effectuer pour qualifier un usage métier.

## Mesures

L’appariement des actions utilise des groupes de concepts annotés. Chaque groupe doit avoir au moins un alias présent dans la description, après passage en minuscules, décomposition des accents et segmentation en mots. Un chemin augmentant calcule un appariement biparti de cardinalité maximale. Un élément ne peut servir qu’une fois. Les égalités sont départagées par l’ordre des entrées. Les identifiants d’actions de référence et les associations avec les prédictions sont exportés par cas.

| Mesure | Calcul |
|---|---|
| Précision / rappel | Vrais positifs parmi les actions prédites / parmi les actions attendues |
| F1 | 2 VP / (2 VP + FP + FN) |
| Fausses actions | FP / (VP + FP) |
| Responsables, dates, statuts | Exactitudes sur les appariements, y compris les inconnues attendues |
| Avancements exacts | Observations annotées dont le concept et le statut sont retrouvés |
| Citations valides | Extraits présents dans la note normalisée, toutes sections confondues |
| Parsing et traitement | Parts des cas ayant échoué au schéma, et toutes causes confondues |
| Latence et tokens | Durée moyenne des appels observés par cas et sommes des tokens rapportés |

Un dénominateur nul est représenté par null. Un échec garde les actions attendues comme faux négatifs. L’exactitude des nombres de décisions et de problèmes et le signalement des ambiguïtés complètent les mesures. Une ambiguïté est signalée par une clarification ou un indicateur de revue. Les synonymes absents, les négations et les tâches partageant le même objet exigent une inspection des appariements.

## Exécuter

```bash
python scripts/evaluate.py
python scripts/evaluate.py --predictions predictions.json --output evaluation-results-offline.json
```

La première commande contrôle l’inventaire. La seconde accepte une table JSON associant les identifiants C01 à C21 à des ExtractionResult sérialisés.

Après configuration d’une clé et autorisation du coût :

```bash
python scripts/evaluate.py --live --limit 2 --output evaluation-results-mini.json
MAX_API_CALLS_PER_SESSION=42 python scripts/compare_models.py --live --limit 21
```

Avec une seule tentative, la seconde commande autorise jusqu’à 42 requêtes, réparties entre `OPENAI_MODEL` et `OPENAI_EVAL_MODEL`. Pour limiter les coûts, réduire le nombre de cas. Les fichiers par modèle contiennent les comptes par cas, les appariements, les erreurs et les agrégats. La commande affiche le tableau comparatif. Le budget doit couvrir les deux séries. Aucune campagne GPT réelle n’a été exécutée lors de la livraison.

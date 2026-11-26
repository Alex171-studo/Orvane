# Architecture et contrats

ORVANE est un monolithe Python 3.12. Streamlit possède les widgets et la session. Le domaine, les adaptateurs et les services se testent sans serveur web.

| Couche | Responsabilité |
|---|---|
| Domaine | Modèles stricts, données sources, états, propositions et révisions |
| Fournisseurs | Requêtes SDK, conversion des erreurs, compteurs et observations de latence |
| Services | Normalisation, contrôle des citations et liens, calendrier, workflow, analytics et rendu A4 |
| Repository | Données de la session, export typé et import atomique |
| Interface | Consentement, correction, revue, validation et téléchargement |

## Parcours d’une note

```text
NEW → TRANSCRIBED → TRANSCRIPT_APPROVED → ANALYZED → IN_REVIEW → VALIDATED → EXPORTED
```

Un enregistrement ou un fichier importé passe du navigateur à la mémoire du serveur Streamlit. Le SDK Groq transmet directement les octets dans un fichier multipart anonyme. Les données de langue, durée et segments restent facultatives. L’heure de référence est fixée à midi dans le fuseau du chantier pour la date de visite choisie. Une note saisie au clavier rejoint le même circuit de validation.

La méthode `FieldIntelligencePipeline.analyze(transcript, project_context, reference_datetime)` prépare le texte, appelle le fournisseur configuré et matérialise une `ExtractionResult`. Le SDK OpenAI construit le schéma strict depuis `Proposal`. L’adaptateur examine le statut de complétion avant de laisser le helper parser la réponse, afin de distinguer une limite de sortie et un résultat mal formé. Les UUID sont attribués en Python. Les indices de relations sont vérifiés avant leur conversion en identifiants.

La correction d’une transcription invalide son approbation et le brouillon associé. Un rapport publié garde sa propre copie du texte source. Modifier son contenu ou une action crée une nouvelle révision en revue. Une validation explicite publie la version. Le journal conserve les valeurs avant/après des corrections dans la session privée.

## Mesures

Les rapports validés sont dénombrés par note. Les problèmes ouverts possèdent un indicateur éditable. Une action ouverte a un statut différent de « Terminée ». Une action ouverte est en retard quand sa date d’échéance précède le jour courant du chantier. La durée moyenne calculée porte sur les tentatives fournisseur réussies et observées. Le modèle retourné par OpenAI, l’identifiant de requête et les tokens sont conservés quand ils sont disponibles.

Le taux de correction mesure la part des éléments proposés (synthèses comprises) touchés par une modification ou suppression. Une création manuelle compte dans le volume de corrections. Plusieurs éditions du même élément initial ne multiplient pas le numérateur du taux.

## Session et export

Une instance de SessionRepository et de CallRuntime appartient à chaque session Streamlit. Une empreinte lie une transcription au contenu audio, au modèle et à la langue. Une extraction réutilisable dépend du texte normalisé, du contexte, du modèle, du budget et du prompt. Les mesures privées et les résultats sont en mémoire.

L’archive JSON version 1 est relue intégralement avant remplacement. Le contrôle porte sur le schéma, les références chantier/note, les identifiants, les révisions, les états et les citations des rapports validés. La limite d’import est de 12 Mo. Le budget des appels en cours de session reste côté serveur. La restauration et la réinitialisation vident les résultats réutilisables. Les audios et secrets restent hors archive.

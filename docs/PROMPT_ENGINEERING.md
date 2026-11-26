# Extraction et traçabilité

Le registre sélectionne `v1` ou `v2`. V1 définit le contrat de chantier, la fidélité, les rôles, les échéances, les statuts et les citations. V2 ajoute des exemples contrastant suggestion et décision, des notes contradictoires, des répétitions, des responsabilités rapportées et plusieurs chantiers.

Les instructions sont passées dans `instructions`. Le texte, le lieu, le nom du chantier et la date sont sérialisés comme données dans un message utilisateur. L’application n’offre aucun outil au modèle. Les champs de propositions sont obligatoires et les inconnues utilisent des types nullables. Le helper SDK génère le schéma Structured Outputs et parse directement les objets Pydantic.

Les échéances sont extraites sous leur forme littérale. Le calendrier Python reconnaît les dates ISO, jour/mois/année, les mois français avec année, aujourd’hui, demain, après-demain et « dans N jours ». Pour un jour de la semaine seul, une échéance correspond à la prochaine occurrence après la visite. Si la visite a lieu ce même jour, l’échéance reste à confirmer. Une expression non reconnue ou absente de la citation reste sans date et entraîne une clarification. Les noms absents de la citation sont remplacés par une valeur inconnue assortie d’une clarification.

La normalisation NFC et des espaces rend comparables les citations et la note sans supprimer les accents. Une citation introuvable empêche la validation finale. Les relations hors limites et doublons bloquent le résultat incohérent. Une citation réelle peut étayer une mauvaise interprétation, notamment une négation, un pronom ou un responsable simplement mentionné. La relecture humaine porte aussi sur le sens de la synthèse, les oublis et le rattachement au chantier.

Pour faire évoluer le prompt, ajouter une version au registre, conserver les versions utilisées en comparaison, rejouer la suite hors ligne puis évaluer les deux versions avec les mêmes cas et les mêmes paramètres. Examiner les erreurs par dossier avant de modifier les consignes. [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

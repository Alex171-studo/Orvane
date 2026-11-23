from .extraction_v1 import SYSTEM as BASE

SYSTEM = (
    BASE
    + """
« La dalle est coulée » décrit un avancement terminé, sans nouvelle action.
« On pourrait déplacer la grue » est une suggestion. « Déplacement validé en réunion » est une décision.
« Karim doit appeler le fournisseur demain » donne une action attribuée à Karim avec « demain »
comme échéance. « Rapidement » reste littéral et appelle une clarification.
Si deux intervenants se contredisent sur la réception, conserver l'incertitude dans la synthèse.
Si plusieurs sites sont nommés, isoler les informations du site sélectionné et demander à quel
site rattacher les éléments ambigus. La répétition d'une consigne ne crée pas plusieurs tâches.
La personne qui rapporte une tâche n'en est pas nécessairement responsable."""
)

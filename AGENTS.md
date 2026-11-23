# Développer ORVANE

Utiliser Python 3.12 avec les versions dans requirements-dev.txt. Lancer Ruff et Pytest depuis la racine. Les tests doivent pouvoir s’exécuter sans identifiants et sans trafic fournisseur.

Conserver les règles de chantier, le PDF, les statistiques et les transitions dans src/services. Les adaptateurs Groq et OpenAI restent les seuls clients externes. Toute nouvelle opération facturable doit passer par CallRuntime et une action explicite dans l’interface.

Lorsque le contrat de sortie change, vérifier le schéma Structured Outputs, les fixtures, le corpus annoté et la compatibilité de l’archive. Toute modification d’un compte rendu validé passe par une révision et la revue humaine.

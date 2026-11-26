"""Évaluer le corpus explicitement, ou vérifier son intégrité hors ligne."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.config.settings import Settings
from src.providers.openai_extraction import OpenAIExtractionService
from src.providers.runtime import CallRuntime
from src.services.evaluation_service import corpus, evaluate
from src.services.extraction_service import FieldIntelligencePipeline


def run(cfg, pairs, live, predictions=None):
    if live:
        if len(pairs) > cfg.MAX_API_CALLS_PER_SESSION:
            raise SystemExit(
                "Lot supérieur au budget. Réduisez --limit ou configurez MAX_API_CALLS_PER_SESSION."
            )
        runtime = CallRuntime(cfg)
        pipeline = FieldIntelligencePipeline(OpenAIExtractionService(cfg, runtime), cfg)
        return evaluate(pairs, cfg.OPENAI_MODEL, cfg.PROMPT_VERSION, pipeline, runtime)
    return evaluate(pairs, "prédictions importées", cfg.PROMPT_VERSION, predictions=predictions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--live", action="store_true", help="Autoriser les appels facturables OpenAI."
    )
    group.add_argument(
        "--predictions",
        type=Path,
        help="Objet JSON associant chaque ID de cas à son ExtractionResult.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, default=Path("evaluation-results.json"))
    args = parser.parse_args()
    pairs = corpus()
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit doit être positif")
        pairs = pairs[: args.limit]
    if not (args.live or args.predictions):
        print(f"{len(pairs)} scénarios annotés disponibles. Aucun appel fournisseur.")
        return
    predictions = json.loads(args.predictions.read_text()) if args.predictions else None
    report = run(Settings.load(), pairs, args.live, predictions)
    args.output.write_text(report.model_dump_json(indent=2))
    print(pd.Series(report.scores, name=report.model).to_string())


if __name__ == "__main__":
    main()

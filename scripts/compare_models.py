import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from scripts.evaluate import run
from src.config.settings import Settings
from src.services.evaluation_service import corpus


def main():
    p = argparse.ArgumentParser(description="Comparer les deux modèles sur les mêmes cas.")
    p.add_argument("--live", action="store_true", help="Autoriser la facturation des deux séries.")
    p.add_argument("--limit", type=int, default=21)
    args = p.parse_args()
    if not args.live:
        print("Comparaison inactive. Utilisez --live pour autoriser les appels.")
        return
    cfg = Settings.load()
    pairs = corpus()[: args.limit]
    if args.limit < 1 or 2 * len(pairs) * cfg.MAX_ATTEMPTS > cfg.MAX_API_CALLS_PER_SESSION:
        p.error("Le budget doit couvrir les deux séries et les éventuelles tentatives.")
    summaries = {}
    for model in (cfg.OPENAI_MODEL, cfg.OPENAI_EVAL_MODEL):
        report = run(cfg.model_copy(update={"OPENAI_MODEL": model}), pairs, True)
        Path("evaluation-results-" + model + ".json").write_text(report.model_dump_json(indent=2))
        summaries[model] = report.scores
    print(pd.DataFrame(summaries).to_string())


if __name__ == "__main__":
    main()

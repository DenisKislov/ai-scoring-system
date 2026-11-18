"""Grouped out-of-fold spaCy training on the frozen presentation JSON corpus.

The JSON inputs and reference skills are never rewritten. Document-level OOF
predictions are distinct from a single deployable model's benchmark results.
"""
from __future__ import annotations

import os

# Set before numerical libraries are imported in spawned training processes.
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_key] = "1"

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import re
import shutil
import statistics
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scorer.corpus import resume_text_of, vacancy_text_of
from scorer.privacy import professional_text
from scorer.ner_skills import _clean_text
from scorer.skills import normalize_skill_set
from training.ner.span_match import build_entities, default_alias_map

INPUTS = {"vacancies": "superjob_dataset.json", "resumes": "dataset_resume.json"}
METRIC_LIMITS = {"ndcg_at_10": .9, "precision_at_5": .9,
                 "precision_at_10": .9, "recall_at_10": .15, "spearman_score": .8}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_records(directory):
    records, hashes = [], {}
    for kind, filename in INPUTS.items():
        path = directory / filename
        hashes[filename] = digest(path)
        rows = json.loads(path.read_text())
        adapt = vacancy_text_of if kind == "vacancies" else resume_text_of
        for index, row in enumerate(rows):
            original = adapt(row)
            text = _clean_text(professional_text(original))
            records.append({"key": f"{kind}/{index:03}", "kind": kind,
                            "index": index, "source": row.get("_source") or "rich-json",
                            "text": text, "original_text": original,
                            "truth": sorted(normalize_skill_set(set(row.get("expected_skills") or [])))})
    return records, hashes


def text_groups(records):
    """Keep exact and conservatively detected near copies in one fold."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    words = [re.findall(r"\w+", r["text"].casefold().replace("ё", "е")) for r in records]
    grams = [set(zip(*(w[offset:] for offset in range(5)))) for w in words]
    identities = [" ".join(w) for w in words]
    for i in range(len(records)):
        for j in range(i):
            same = bool(identities[i]) and identities[i] == identities[j]
            if not same and min(len(words[i]), len(words[j])) >= 30:
                a, b = grams[i], grams[j]
                common = len(a & b)
                same = (common / len(a | b) >= .7 or
                        common / min(len(a), len(b)) >= .85) if a and b else False
            if same:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(records)):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=lambda group: tuple(records[i]["key"] for i in group))


def make_folds(records, count=5, seed=20261118):
    groups = text_groups(records)
    shuffled = list(groups)
    random.Random(seed).shuffle(shuffled)
    shuffled.sort(key=lambda g: (-sum(records[i]["kind"] == "vacancies" for i in g), -len(g)))
    folds = [[] for _ in range(count)]
    for group in shuffled:
        has_vacancy = any(records[i]["kind"] == "vacancies" for i in group)
        fold = min(range(count), key=lambda k: (
            sum(records[i]["kind"] == "vacancies" for i in folds[k]) if has_vacancy else len(folds[k]),
            len(folds[k]), k))
        folds[fold].extend(group)
    return [sorted(fold) for fold in folds], groups


def inner_split(records, groups, test, seed):
    test = set(test)
    candidates = [g for g in groups if not set(g) & test]
    random.Random(seed).shuffle(candidates)
    target = max(1, round(sum(map(len, candidates)) * .2))
    monitor, fit = [], []
    for group in candidates:
        (monitor if len(monitor) < target else fit).extend(group)
    if not fit or not monitor:
        raise ValueError("Insufficient groups for an inner validation split")
    return sorted(fit), sorted(monitor)


def new_model(seed):
    import spacy
    from spacy.util import fix_random_seed
    fix_random_seed(seed)
    nlp = spacy.load("ru_core_news_sm", exclude=[
        "tok2vec", "morphologizer", "parser", "attribute_ruler", "lemmatizer"])
    nlp.get_pipe("ner").add_label("Skill")
    return nlp


def reference_docs(nlp, records, indices):
    aliases = default_alias_map()
    docs, counts = [], Counter()
    for i in indices:
        r = records[i]
        entities, stats = build_entities(nlp, r["text"], r["truth"], aliases)
        counts.update(stats)
        doc = nlp.make_doc(r["text"])
        doc.ents = [doc.char_span(s, e, label=label) for s, e, label in entities]
        # Keep entity boundaries intact when chunking long training documents.
        start = 0
        while start < len(doc):
            end = min(start + 240, len(doc))
            for ent in doc.ents:
                if ent.start < end < ent.end:
                    end = ent.end
            docs.append(doc[start:end].as_doc())
            start = end
    return docs, dict(counts)


def examples_for(nlp, docs):
    from spacy.training import Example
    return [Example(nlp.make_doc(doc.text), doc) for doc in docs]


def span_metrics(nlp, docs):
    from spacy.training import Example
    from spacy.scorer import Scorer
    examples = []
    for predicted, reference in zip(nlp.pipe([d.text for d in docs], batch_size=8), docs):
        predicted.ents = [e for e in predicted.ents if e.label_ == "Skill"]
        examples.append(Example(predicted, reference))
    result = Scorer().score(examples)
    return {k: float(result[k]) for k in ("ents_p", "ents_r", "ents_f")}


def hybrid_prediction(nlp, text):
    """Use exactly the existing production dictionary/NER merge policy."""
    from scorer import skills as module
    doc = nlp(_clean_text(professional_text(text)))
    entities = {e.text.strip() for e in doc.ents if e.label_ == "Skill" and e.text.strip()}
    with patch.object(module, "ner_enabled", lambda: True), \
            patch.object(module, "ner_extract_skills", lambda _: entities):
        return sorted(module.extract_skills(text)), sorted(normalize_skill_set(entities))


def clean_checkpoint(raw, clean, nlp, texts):
    import spacy
    from training.ner.sanitize_model import sanitize
    before = [[(e.start_char, e.end_char, e.label_) for e in nlp(text).ents] for text in texts]
    cleanup = sanitize(raw, clean)
    loaded = spacy.load(clean)
    after = [[(e.start_char, e.end_char, e.label_) for e in loaded(text).ents] for text in texts]
    if before != after:
        raise RuntimeError("Vocabulary cleanup changed entity predictions")
    return loaded, {**cleanup, "compared_documents": len(texts), "predictions_equal": True}


def train_fold(task):
    import spacy
    from spacy.util import minibatch
    records, fit, monitor, test, config, directory = task
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    nlp = new_model(config["seed"])
    fit_docs, fit_coverage = reference_docs(nlp, records, fit)
    monitor_docs, monitor_coverage = reference_docs(nlp, records, monitor)
    examples = examples_for(nlp, fit_docs)
    optimizer = nlp.resume_training()
    optimizer.learn_rate = .0005
    rng = random.Random(config["seed"])
    best, best_epoch, stale, history = -1, 0, 0, []
    raw = directory / "raw-best"
    for epoch in range(1, config["epochs"] + 1):
        rng.shuffle(examples)
        losses = {}
        for batch in minibatch(examples, size=8):
            nlp.update(batch, sgd=optimizer, drop=.2, losses=losses)
        if epoch % 2:
            continue
        metrics = span_metrics(nlp, monitor_docs)
        row = {"epoch": epoch, **metrics, "loss": {k: float(v) for k, v in losses.items()}}
        history.append(row)
        with (directory / "progress.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        if metrics["ents_f"] > best + .0001:
            best, best_epoch, stale = metrics["ents_f"], epoch, 0
            nlp.to_disk(raw)
        else:
            stale += 1
        if epoch >= 6 and stale >= 3:
            break
    nlp = spacy.load(raw)
    texts = [records[i]["text"] for i in test]
    nlp, cleanup = clean_checkpoint(raw, directory / "model", nlp, texts)
    predictions = {}
    for i in test:
        hybrid, ner = hybrid_prediction(nlp, records[i]["original_text"])
        predictions[str(i)] = {"hybrid": hybrid, "ner_only": ner}
    test_docs, test_coverage = reference_docs(nlp, records, test)
    result = {"fit_keys": [records[i]["key"] for i in fit],
              "monitor_keys": [records[i]["key"] for i in monitor],
              "test_keys": [records[i]["key"] for i in test],
              "best_epoch": best_epoch, "monitor_span_f1": best,
              "test_span_metrics": span_metrics(nlp, test_docs), "history": history,
              "coverage": {"fit": fit_coverage, "monitor": monitor_coverage, "test": test_coverage},
              "cleanup": cleanup, "predictions": predictions,
              "model_files": {str(p.relative_to(directory / "model")): digest(p)
                              for p in sorted((directory / "model").rglob("*")) if p.is_file()}}
    write_json(directory / "result.json", result)
    shutil.rmtree(raw)
    return result


def train_final(records, epochs, config, directory):
    from spacy.util import minibatch
    directory.mkdir(parents=True, exist_ok=True)
    nlp = new_model(config["seed"])
    docs, coverage = reference_docs(nlp, records, list(range(len(records))))
    examples = examples_for(nlp, docs)
    optimizer = nlp.resume_training()
    optimizer.learn_rate = .0005
    rng = random.Random(config["seed"])
    for epoch in range(1, epochs + 1):
        rng.shuffle(examples)
        losses = {}
        for batch in minibatch(examples, size=8):
            nlp.update(batch, sgd=optimizer, drop=.2, losses=losses)
        with (directory / "progress.jsonl").open("a") as handle:
            handle.write(json.dumps({"epoch": epoch, "loss": {k: float(v) for k, v in losses.items()}}) + "\n")
    raw = directory / "raw-model"
    nlp.to_disk(raw)
    nlp, cleanup = clean_checkpoint(raw, directory / "model", nlp, [r["text"] for r in records])
    predictions = [hybrid_prediction(nlp, r["original_text"])[0] for r in records]
    result = {"epochs": epochs, "epoch_selection": "median inner-validation best epoch, not outer test metrics",
              "fit_documents": len(records), "coverage": coverage, "cleanup": cleanup,
              "predictions": predictions, "evaluation_scope": "in_sample_only",
              "model_files": {str(p.relative_to(directory / "model")): digest(p)
                              for p in sorted((directory / "model").rglob("*")) if p.is_file()}}
    write_json(directory / "result.json", result)
    shutil.rmtree(raw)
    return result


def evaluate_predictions(records, predictions, subset=None):
    from scorer.scoring import rank_candidates
    from scorer.metrics import ndcg, precision_at_k, recall_at_k, spearman, category_metrics
    selected = set(range(len(records))) if subset is None else set(subset)
    resume_ids = [i for i, r in enumerate(records) if r["kind"] == "resumes" and i in selected]
    vacancy_ids = [i for i, r in enumerate(records) if r["kind"] == "vacancies" and i in selected]
    extraction = {}
    for kind in INPUTS:
        counts = Counter(tp=0, fp=0, fn=0, documents=0)
        categories = defaultdict(Counter)
        for i, record in enumerate(records):
            if i not in selected or record["kind"] != kind:
                continue
            truth = {s.casefold() for s in record["truth"]}
            pred = {s.casefold() for s in normalize_skill_set(set(predictions[i]))}
            counts.update(tp=len(truth & pred), fp=len(pred - truth), fn=len(truth - pred), documents=1)
            for category, values in category_metrics(set(predictions[i]), set(record["truth"])).items():
                categories[category].update({k: values[k] for k in ("tp", "fp", "fn")})
        def prf(values):
            tp, fp, fn = (values[k] for k in ("tp", "fp", "fn"))
            p, r = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
            return {**values, "precision": p, "recall": r, "f1": 2*p*r/(p+r) if p+r else 0}
        extraction[kind] = {"micro": prf(counts), "categories": {k: prf(v) for k, v in categories.items()}}
    queries = []
    for vi in vacancy_ids:
        vacancy = records[vi]
        truth_v = set(vacancy["truth"])
        truth = {i: len(truth_v & set(records[i]["truth"])) / len(truth_v) if truth_v else 0 for i in resume_ids}
        ranked = rank_candidates(vacancy["original_text"], [records[i]["original_text"] for i in resume_ids],
                                 candidate_ids=resume_ids, vacancy_skills=set(predictions[vi]),
                                 resume_skills_list=[set(predictions[i]) for i in resume_ids])
        relevance = [truth[row["candidate_id"]] for row in ranked]
        scores = {row["candidate_id"]: row["score"] for row in ranked}
        queries.append({"vacancy_key": vacancy["key"], "candidate_pool": len(resume_ids),
                        "ndcg_at_10": ndcg(relevance, 10), "precision_at_5": precision_at_k(relevance, 5, .1),
                        "precision_at_10": precision_at_k(relevance, 10, .1), "recall_at_10": recall_at_k(relevance, 10, .1),
                        "spearman_score": spearman([scores[i] for i in resume_ids], [truth[i] for i in resume_ids])})
    mean = {}
    for key in METRIC_LIMITS:
        values = [q[key] for q in queries if q[key] is not None]
        mean[key] = statistics.mean(values) if values else None
    return {"extraction": extraction, "ranking": {"mean": mean, "queries": queries},
            "numeric_thresholds": {k: {"value": mean[k], "minimum": v,
                                        "passed": mean[k] is not None and mean[k] >= v}
                                   for k, v in METRIC_LIMITS.items() if k in mean}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "data/benchmark")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--epochs", type=int, default=24)
    args = parser.parse_args()
    if args.epochs < 2 or args.output_dir.exists():
        parser.error("Use epochs >= 2 and a new output directory")
    records, hashes = load_records(args.dataset_dir)
    if Counter(r["kind"] for r in records) != {"resumes": 194, "vacancies": 10}:
        parser.error("Expected the frozen presentation corpus: 10 vacancies, 194 resumes")
    folds, groups = make_folds(records)
    config = {"seed": 20261118, "epochs": args.epochs, "folds": 5,
              "base_model": "ru_core_news_sm", "base_model_version": importlib.metadata.version("ru_core_news_sm"),
              "spacy_version": importlib.metadata.version("spacy"), "automatic_span_labels": True}
    args.output_dir.mkdir(parents=True)
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "input_files": hashes, "config": config,
                "training_script_sha256": digest(__file__),
                "groups": [[records[i]["key"] for i in g] for g in groups],
                "fold_test_keys": [[records[i]["key"] for i in fold] for fold in folds]}
    write_json(args.output_dir / "manifest.json", manifest)
    tasks = []
    for k, test in enumerate(folds):
        fit, monitor = inner_split(records, groups, test, config["seed"] + k)
        tasks.append((records, fit, monitor, test, {**config, "seed": config["seed"] + k}, args.output_dir / f"fold_{k}"))
    print(json.dumps({"stage": "training", "documents": len(records), "groups": len(groups),
                      "fold_sizes": [len(f) for f in folds]}, ensure_ascii=False), flush=True)
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(train_fold, task): k for k, task in enumerate(tasks)}
        for future in as_completed(futures):
            k = futures[future]
            results[k] = future.result()
            print(json.dumps({"stage": "fold_finished", "fold": k, "best_epoch": results[k]["best_epoch"],
                              "test_span_metrics": results[k]["test_span_metrics"]}), flush=True)
    oof, ner_only, owners = {}, {}, {}
    for k, result in results.items():
        for raw, values in result["predictions"].items():
            i = int(raw)
            if i in oof or records[i]["key"] in result["fit_keys"] + result["monitor_keys"]:
                raise RuntimeError("Leaked or repeated out-of-fold prediction")
            oof[i], ner_only[i], owners[i] = values["hybrid"], values["ner_only"], k
    if len(oof) != len(records):
        raise RuntimeError("Missing out-of-fold predictions")
    report = {"manifest": manifest, "input_files_unchanged": True,
              "scope": "OOF entity extraction; cross-fitted ranking combines document predictions from five models",
              "out_of_fold": evaluate_predictions(records, oof),
              "ner_only_out_of_fold": evaluate_predictions(records, ner_only),
              "document_predictions": [{"key": r["key"], "fold": owners[i], "skills": oof[i],
                                         "ner_only_skills": ner_only[i]} for i, r in enumerate(records)],
              "folds": {str(k): {key: value for key, value in results[k].items() if key != "predictions"} for k in sorted(results)},
              "limitations": ["Spans were generated by label/alias matching, not independently annotated by experts.",
                              "Historical production vocabulary was adjusted using this corpus; only NER training is held out here.",
                              "Cross-fitted full-pool ranking is not the benchmark of one deployable model.",
                              "Strict fold-pool rankings use smaller candidate pools and cannot be compared directly with 194 candidates."]}
    strict = []
    import spacy
    for k, test in enumerate(folds):
        nlp = spacy.load(args.output_dir / f"fold_{k}/model")
        predictions = {i: hybrid_prediction(nlp, records[i]["original_text"])[0] for i in test}
        evaluation = evaluate_predictions(records, predictions, test)
        strict.append({"fold": k, **evaluation})
    report["strict_same_model_fold_pools"] = strict
    final_epochs = round(statistics.median(r["best_epoch"] for r in results.values()))
    print(json.dumps({"stage": "final_training", "epochs": final_epochs,
                      "oof_ranking": report["out_of_fold"]["ranking"]["mean"]}), flush=True)
    final = train_final(records, final_epochs, config, args.output_dir / "final")
    report["final_model"] = {k: v for k, v in final.items() if k != "predictions"}
    report["final_model"]["path"] = str((args.output_dir / "final/model").resolve())
    report["final_model"]["in_sample_evaluation"] = evaluate_predictions(records, dict(enumerate(final["predictions"])))
    for filename, expected in hashes.items():
        if digest(args.dataset_dir / filename) != expected:
            raise RuntimeError("Input corpus changed during training")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(args.report_dir / "cross_validation.json", report)
    write_json(args.report_dir / "manifest.json", manifest)
    print(json.dumps({"stage": "complete", "oof_ranking": report["out_of_fold"]["ranking"]["mean"],
                      "model": report["final_model"]["path"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

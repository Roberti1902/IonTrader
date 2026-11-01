"""Phase 3: Modell-Turnier im Walk-Forward. Jeder Typ nur auf dem Ticker und auf dem Universum plus Feinschliff."""
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
import torch

from . import ROOT
from .dataset import FOLD_DAYS, HORIZON_DAYS, HORIZON_NAMES, INPUT, Bundle, fold_dates, load_ticker
from .models import KINDS, TAUS, IonNet, loss_fn, target_losses
from .store import connect, replace_rows
from .universe import available

MODELS = ROOT / "data" / "models"
OOS = ROOT / "data" / "oos"
REPORTS = ROOT / "reports"
BATCH = 512
INPUT_NOISE = 0.1
MIN_T = 2.0  # So klar muss ein Stand die Basis im Auswahlfenster schlagen, gemessen auf unabhaengigen Bloecken
MIN_GAIN = 1e-4


class Selector:
    """Merkt sich je Ziel (Horizont x Richtung/Spanne) den besten Stand, der die Basis belegbar schlaegt.

    Stand 0 ist die Basis. Kann das Netz ein Ziel im Auswahlfenster nicht klar schlagen, bleibt es auf der Basis.
    Bei langen Horizonten passen kaum unabhaengige Bloecke ins Fenster; sie bleiben deshalb meist auf der Basisrate.
    """

    def __init__(self, weights, mask, blocks):
        self.weights, self.mask, self.blocks = weights, mask, blocks  # mask, blocks: (Beispiele, Horizonte)
        self.states, self.next_id, self.base = {}, 0, None
        self.best = self.which = None
        self.overall_best, self.overall_id = np.inf, -1

    def _means(self, loss):
        return np.array([loss[self.mask[:, h], h].mean() if self.mask[:, h].any() else np.inf for h in range(loss.shape[1])])

    def _t_vs_base(self, loss, base):
        out = np.zeros(loss.shape[1])
        for h in range(loss.shape[1]):
            m = self.mask[:, h]
            if not m.any():
                continue
            _, group = np.unique(self.blocks[m, h], return_inverse=True)
            n = group.max() + 1
            if n < 3:
                continue
            count = np.bincount(group, minlength=n)
            diff = np.bincount(group, weights=base[m, h] - loss[m, h], minlength=n) / count
            spread = diff.std(ddof=1)
            out[h] = diff.mean() / (spread / np.sqrt(n)) if spread > 0 else 0.0
        return out

    def update(self, bce, pinball, model):
        """bce, pinball: (Beispiele, Horizonte). Liefert True, wenn es Fortschritt gab."""
        losses = np.stack([self._means(bce), self._means(pinball)], axis=1)
        finite = np.isfinite(losses)
        total = float((np.where(finite, losses, 0).sum(1) * self.weights).sum())
        if self.base is None:
            self.base = (bce, pinball)
            self.best, self.which = losses.copy(), np.zeros_like(losses, dtype=np.int64)
            improved = np.ones_like(losses, dtype=bool)
        else:
            t = np.stack([self._t_vs_base(bce, self.base[0]), self._t_vs_base(pinball, self.base[1])], axis=1)
            improved = (t >= MIN_T) & (losses < self.best - MIN_GAIN)
        better_overall = total < self.overall_best - MIN_GAIN
        if improved.any() or better_overall:
            self.states[self.next_id] = {k: v.detach().clone() for k, v in model.state_dict().items()}
            self.best[improved], self.which[improved] = losses[improved], self.next_id
            if better_overall:
                self.overall_best, self.overall_id = total, self.next_id
            self.next_id += 1
            keep = set(self.which.ravel().tolist()) | {self.overall_id}
            self.states = {k: v for k, v in self.states.items() if k in keep}
        return bool(improved.any() or better_overall)

    def predict(self, model, bundle, idx):
        """Setzt die Vorhersage aus den je Ziel besten Staenden zusammen."""
        logit, q, attention = None, None, None
        for sid in sorted(set(self.which.ravel().tolist())):
            model.load_state_dict(self.states[sid])
            part_logit, part_q, part_att = predict(model, bundle, idx)
            if logit is None:
                logit, q = np.zeros_like(part_logit), np.zeros_like(part_q)
            for h in range(part_logit.shape[1]):
                if self.which[h, 0] == sid:
                    logit[:, h] = part_logit[:, h]
                if self.which[h, 1] == sid:
                    q[:, h] = part_q[:, h]
            attention = part_att
        return logit, q, attention

    def describe(self):
        return " ".join(f"{name}:{'B' if self.which[h, 0] == 0 else 'N'}{'B' if self.which[h, 1] == 0 else 'N'}"
                        for h, name in enumerate(HORIZON_NAMES))


def predict(model, bundle, idx, batch=2048):
    """Roh-Ausgaben ohne Dropout. Liefert logit (n, h), Quantile (n, h, 3) und mittlere Attention (h, tf)."""
    model.eval()
    logits, quantiles, attention = [], [], []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        for i in range(0, len(idx), batch):
            a = idx[i:i + batch]
            logit, q, weights = model(bundle.batch(a), bundle.ticker[a], attention=True)
            logits.append(logit.float().cpu()), quantiles.append(q.float().cpu()), attention.append(weights.float().cpu())
    return torch.cat(logits).numpy(), torch.cat(quantiles).numpy(), torch.cat(attention).mean(0).numpy()


def select_losses(model, bundle, idx, taus, batch=2048):
    """Verlust je Beispiel und Horizont im Auswahlfenster, getrennt nach Richtung und Spanne."""
    model.eval()
    bce_parts, pin_parts = [], []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        for i in range(0, len(idx), batch):
            a = idx[i:i + batch]
            logit, q, _ = model(bundle.batch(a), bundle.ticker[a])
            bce, pinball = target_losses(logit.float(), q.float(), bundle.y[a], bundle.scale_y[a], taus)
            bce_parts.append(bce.cpu()), pin_parts.append(pinball.cpu())
    return torch.cat(bce_parts).numpy(), torch.cat(pin_parts).numpy()


def fit(kind, bundle, idx, label, lr, epochs, checks, patience, state=None, log=print):
    """Trainiert mit vielen Pruefungen je Epoche, weil das Netz bei verrauschten Zielen schnell auswendig lernt."""
    device = bundle.device
    model = IonNet(kind, bundle.dims, bundle.windows, bundle.base_up, bundle.base_q).to(device)
    taus = torch.tensor(TAUS, device=device).view(1, 1, -1)
    weights = 1 / torch.tensor(bundle.horizon_days, dtype=torch.float32, device=device).sqrt()
    select_idx = bundle.select_idx()
    i = select_idx.cpu().numpy()
    blocks = bundle.date[i, None] // np.maximum(1, np.array(bundle.horizon_days))
    selector = Selector(weights.cpu().numpy(), bundle.mask_select[select_idx].cpu().numpy(), blocks)
    selector.update(*select_losses(model, bundle, select_idx, taus), model)  # Stand 0: reine Basis
    if len(idx) < BATCH or len(select_idx) == 0:
        return model, selector
    if state is not None:
        model.load_state_dict(state)
        selector.update(*select_losses(model, bundle, select_idx, taus), model)
    steps = len(idx) // BATCH
    every = max(1, steps // checks)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps * epochs)
    scaler = torch.amp.GradScaler("cuda")
    tic, done, waited = time.perf_counter(), 0, 0
    for epoch in range(epochs):
        order = idx[torch.randperm(len(idx), device=device)]
        stop = False
        for s in range(steps):
            a = order[s * BATCH:(s + 1) * BATCH]
            model.train()
            xs = {tf: x + INPUT_NOISE * torch.randn_like(x) for tf, x in bundle.batch(a).items()}
            optimizer.zero_grad(set_to_none=True)
            ticker = bundle.ticker[a]
            with torch.autocast("cuda", dtype=torch.float16):
                logit, q, _ = model(xs, ticker)
            loss = loss_fn(logit.float(), q.float(), bundle.y[a], bundle.scale_y[a], bundle.mask_train[a].float(), taus,
                           weights, model.base_logit[ticker])
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            schedule.step()
            done += 1
            if done % every == 0:
                progress = selector.update(*select_losses(model, bundle, select_idx, taus), model)
                waited = 0 if progress else waited + 1
                if waited > patience:
                    stop = True
                    break
        if stop:
            break
    seconds = time.perf_counter() - tic
    log(f"  {label}: {done} Schritte, {seconds:.0f} s, {done * BATCH / max(seconds, 1e-9):,.0f} Beispiele/s, "
        f"GPU {torch.cuda.max_memory_allocated() / 2**30:.1f} GB, Auswahl {selector.describe()} (B=Basis, N=Netz; Richtung, Spanne)")
    return model, selector


def block_ci(model_err, base_err, blocks, n_boot=2000, seed=0):
    """95 %-Intervall der Skill per Block-Bootstrap, weil sich Ereignisse innerhalb eines Horizonts ueberlappen."""
    frame = pd.DataFrame({"m": model_err, "b": base_err}).groupby(np.asarray(blocks)).sum().to_numpy()
    if len(frame) < 3:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    samples = frame[rng.integers(0, len(frame), (n_boot, len(frame)))].sum(1)
    return tuple(np.quantile(1 - samples[:, 0] / samples[:, 1], [0.025, 0.975]))


def skill_scores(oos):
    """Je Horizont: Brier Skill gegen die Basisrate; Pinball Skill gegen feste Quantile und gegen HAR; Trefferquote."""
    taus = np.array(TAUS)
    rows = []
    for h, name in enumerate(HORIZON_NAMES):
        m = oos["mask"][:, h]
        if m.sum() == 0:
            rows.append({"horizont": name, "n": 0})
            continue
        y = oos["y"][m, h]
        up = (y > 0).astype(float)
        p = 1 / (1 + np.exp(-oos["logit"][m, h]))
        base = oos["base_up"][m, h]
        err_model, err_base = (p - up) ** 2, (base - up) ** 2
        scale = oos["scale"][m, h][:, None]
        pin = lambda quant: np.maximum(taus * (y[:, None] - quant), (taus - 1) * (y[:, None] - quant)).mean(1)
        pin_model, pin_har, pin_fixed = pin(oos["q"][m, h] * scale), pin(oos["base_q"][m, h] * scale), pin(oos["fixed_q"][m, h])
        blocks = oos["date"][m] // HORIZON_DAYS[name]  # Tage sind Kalendertage, die Bloecke also auch
        low, high = block_ci(err_model, err_base, blocks)
        pin_low, pin_high = block_ci(pin_model, pin_har, blocks)
        har_low, har_high = block_ci(pin_har, pin_fixed, blocks)
        rows.append({"horizont": name, "n": int(m.sum()), "n_unabh": int(len(np.unique(blocks))),
                     "brier_skill": 1 - err_model.sum() / err_base.sum(), "brier_low": low, "brier_high": high,
                     "pinball_skill": 1 - pin_model.sum() / pin_har.sum(), "pinball_low": pin_low, "pinball_high": pin_high,
                     "har_skill": 1 - pin_har.sum() / pin_fixed.sum(), "har_low": har_low, "har_high": har_high,
                     "gesamt_skill": 1 - pin_model.sum() / pin_fixed.sum(),
                     "treffer": float(((p > 0.5) == (up > 0.5)).mean()), "immer_bull": float(up.mean()),
                     "basis_treffer": float(((base > 0.5) == (up > 0.5)).mean()),
                     "p_mittel": float(p.mean()), "p_streuung": float(p.std())})
    return rows


def fold_output(selector, model, bundle):
    """Vorhersagen fuer das Testjahr. Weder Training noch Auswahl haben diese Zeit gesehen."""
    idx = bundle.test_idx()
    logit, q, attention = selector.predict(model, bundle, idx)
    i = idx.cpu().numpy()
    n = len(i)
    return {"anchor": i, "date": bundle.date[i], "logit": logit, "q": q, "y": bundle.y[idx].cpu().numpy(),
            "mask": bundle.mask_test[idx].cpu().numpy(), "scale": bundle.scale_y[idx].cpu().numpy(),
            "base_up": np.tile(bundle.base_up[0].cpu().numpy(), (n, 1)),
            "base_q": np.tile(bundle.base_q[0].cpu().numpy(), (n, 1, 1)),
            "fixed_q": np.tile(bundle.fixed_q[0].cpu().numpy(), (n, 1, 1))}, attention


def _merge(parts):
    return {key: np.concatenate([p[key] for p in parts]) for key in parts[0]}


def holdout_folds(target):
    """Die bisher unangetasteten letzten 2 Jahre als zwei Testjahre fuer die Abschlusspruefung."""
    _, holdout = fold_dates(target)
    last = int(target.date.max())
    return [(holdout, holdout + FOLD_DAYS), (holdout + FOLD_DAYS, last + 1)], last + 10 ** 6


def latest_logits(symbol, wanted, log=None):
    """Aktuelle Richtung fuer (Typ, Modus), trainiert mit allem, was bis heute bekannt ist."""
    log = log or (lambda text: print(text, flush=True))
    con = connect()
    torch.manual_seed(7)
    target = load_ticker(con, symbol)
    last = int(target.date.max())
    others = [s for s in available(con) if s != symbol] if any(mode == "universe" for _, mode in wanted) else []
    tickers = [target] + [load_ticker(con, s, columns=target.columns, stride=6) for s in others]
    bundle = Bundle(tickers, last + 1, last + 10 ** 6)
    del tickers
    bundle.set_fold(last + 1, last + 2)
    idx = torch.tensor([len(target.y) - 1], device=bundle.device)
    out = {}
    for kind, mode in wanted:
        solo_idx = bundle.train_idx(only_first=True)
        if mode == "solo":
            model, selector = fit(kind, bundle, solo_idx, f"{kind} heute nur Ticker", lr=1e-4, epochs=6, checks=5, patience=10, log=log)
        else:
            _, pre = fit(kind, bundle, bundle.train_idx(), f"{kind} heute Universum", lr=1e-4, epochs=2, checks=20, patience=10, log=log)
            model, selector = fit(kind, bundle, solo_idx, f"{kind} heute Feinschliff", lr=3e-5, epochs=3, checks=5, patience=6,
                                  state=pre.states[pre.overall_id], log=log)
        out[(kind, mode)] = selector.predict(model, bundle, idx)[0][0]
    return out


def tournament(symbol, kinds=KINDS, n_folds=5, use_universe=True, log=None, final=False):
    log = log or (lambda text: print(text, flush=True))
    symbol = symbol.upper()
    con = connect()
    MODELS.mkdir(parents=True, exist_ok=True)
    OOS.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(7)
    torch.set_float32_matmul_precision("high")
    assert torch.cuda.is_available(), "CUDA nicht verfuegbar"

    tic = time.perf_counter()
    target = load_ticker(con, symbol)
    folds, holdout = holdout_folds(target) if final else fold_dates(target, n_folds)
    suffix = "_final" if final else ""
    others = [s for s in available(con) if s != symbol] if use_universe else []
    tickers = [target] + [load_ticker(con, s, columns=target.columns, stride=6) for s in others]
    bundle = Bundle(tickers, folds[0][0], holdout)
    del tickers
    day = lambda d: pd.Timestamp(d, unit="D").date()
    log(f"Daten: {symbol} + {len(others)} Ticker, {len(bundle.y):,} Anker, {sum(bundle.dims.values())} Features ueber "
        f"{len(bundle.tfs)} Timeframes, {torch.cuda.memory_allocated() / 2**30:.1f} GB auf der GPU, {time.perf_counter() - tic:.0f} s")
    log(f"Testzeitraum {day(folds[0][0])} bis {day(folds[-1][1])}" + (", Abschlusspruefung" if final else f", unangetastet ab {day(holdout)}"))

    results, attentions = [], {}
    for kind in kinds:
        tic = time.perf_counter()
        outputs = {"nur Ticker": []}
        if others:
            outputs["Universum + Feinschliff"] = []
        for f, (start, end) in enumerate(folds):
            bundle.set_fold(start, end)
            solo_idx = bundle.train_idx(only_first=True)
            label = f"{kind} Jahr {f + 1}"
            model, selector = fit(kind, bundle, solo_idx, f"{label} nur Ticker", lr=1e-4, epochs=6, checks=5, patience=10, log=log)
            part, attention = fold_output(selector, model, bundle)
            outputs["nur Ticker"].append(part)
            attentions[f"{kind}|nur Ticker"] = attention.tolist()
            if others:
                pre_model, pre = fit(kind, bundle, bundle.train_idx(), f"{label} Universum", lr=1e-4, epochs=2, checks=20, patience=10, log=log)
                model, selector = fit(kind, bundle, solo_idx, f"{label} Feinschliff", lr=3e-5, epochs=3, checks=5, patience=6,
                                      state=pre.states[pre.overall_id], log=log)
                part, attention = fold_output(selector, model, bundle)
                outputs["Universum + Feinschliff"].append(part)
                attentions[f"{kind}|Universum + Feinschliff"] = attention.tolist()
                del pre_model, pre
            del model, selector
            torch.cuda.empty_cache()
        for mode, parts in outputs.items():
            merged = _merge(parts)
            np.savez(OOS / f"{symbol}_{kind}_{'solo' if mode == 'nur Ticker' else 'universe'}{suffix}.npz", **merged)
            rows = skill_scores(merged)
            for row in rows:
                results.append({"modell": kind, "modus": mode, **row})
            log(f"{kind} / {mode}: Brier " + " ".join(f"{r['horizont']}={100 * r.get('brier_skill', np.nan):+.2f}%" for r in rows)
                + " | Spanne gegen HAR " + " ".join(f"{r['horizont']}={100 * r.get('pinball_skill', np.nan):+.2f}%" for r in rows)
                + " | HAR gegen fest " + " ".join(f"{r['horizont']}={100 * r.get('har_skill', np.nan):+.2f}%" for r in rows))
        log(f"{kind} fertig nach {(time.perf_counter() - tic) / 60:.1f} min")

    scores = pd.DataFrame(results)
    if final:
        return scores
    replace_rows(con, "model_scores", symbol, scores)
    (MODELS / f"{symbol}_attention.json").write_text(json.dumps(attentions), encoding="utf-8")
    path = write_report(symbol, scores, attentions, bundle.tfs, folds, holdout, len(others), len(bundle.y))
    log(f"Report: {path}")
    return scores


def rescore(symbol, n_anchors):
    """Bewertet die gespeicherten Vorhersagen neu, ohne zu trainieren, und schreibt Tabelle und Report neu."""
    con = connect()
    results = []
    modes = (("solo", "nur Ticker"), ("universe", "Universum + Feinschliff"))
    for kind in KINDS:
        for tag, mode in modes:
            with np.load(OOS / f"{symbol}_{kind}_{tag}.npz") as data:
                results += [{"modell": kind, "modus": mode, **row} for row in skill_scores({key: data[key] for key in data.files})]
    scores = pd.DataFrame(results)
    replace_rows(con, "model_scores", symbol, scores)
    attentions = json.loads((MODELS / f"{symbol}_attention.json").read_text(encoding="utf-8"))
    folds, holdout = fold_dates(load_ticker(con, symbol))
    return write_report(symbol, scores, attentions, list(INPUT), folds, holdout, len(available(con)), n_anchors)


def _cell(row, key):
    if pd.isna(row.get(key)):
        return "–"
    prefix = key.split("_")[0]
    low, high = row[f"{prefix}_low"], row[f"{prefix}_high"]
    mark = "**" if low > 1e-6 else ""
    return f"{mark}{100 * row[key]:+.2f} %{mark} ({100 * low:+.1f} bis {100 * high:+.1f})"


def write_report(symbol, scores, attentions, tfs, folds, holdout, n_others, n_anchors):
    REPORTS.mkdir(exist_ok=True)
    day = lambda d: pd.Timestamp(d, unit="D").date()
    lines = [f"# {symbol}: Phase-3-Report", "", f"Stand {datetime.now():%Y-%m-%d %H:%M}. {n_anchors:,} Trainingspunkte, "
             f"{symbol} plus {n_others} weitere Ticker. Walk-Forward über {len(folds)} Testjahre von {day(folds[0][0])} bis {day(holdout)}; "
             "die Zeit danach bleibt für Phase 5 unangetastet.", "",
             "Für jedes Testjahr: Training nur mit dem, was vorher bekannt war; Auswahl des besten Stands auf einem eigenen Zeitfenster "
             "davor; gemessen nur im Testjahr selbst. Ein Netz wird je Ziel nur übernommen, wenn es die Basis im Auswahlfenster belegbar "
             "schlägt (t ≥ 2 auf unabhängigen Blöcken). Sonst bleibt das Ziel auf der Basis und zeigt hier 0 %.", "",
             "In Klammern das 95 %-Intervall; fett, wenn es ganz über null liegt.", ""]
    first = scores[scores.n > 0].drop_duplicates("horizont").set_index("horizont")
    lines += ["## Spanne: Was die Schwankungs-Formel allein leistet", "",
              "HAR = Schwankung aus letztem Tag, letzter Woche und letztem Monat, gegenüber festen Quantilen.", "",
              "| " + " | ".join(HORIZON_NAMES) + " |", "|" + "---:|" * len(HORIZON_NAMES),
              "| " + " | ".join(_cell(first.loc[h].to_dict(), "har_skill") for h in HORIZON_NAMES) + " |", ""]
    tables = (("brier_skill", "Richtung: Brier Skill gegen die Basisrate"), ("pinball_skill", "Spanne: Pinball Skill der Netze gegen HAR"))
    for key, title in tables:
        lines += [f"## {title}", "", "| Modell | Modus | " + " | ".join(HORIZON_NAMES) + " |",
                  "|---|---|" + "---:|" * len(HORIZON_NAMES)]
        for (kind, mode), g in scores.groupby(["modell", "modus"], sort=False):
            by = {r["horizont"]: r for r in g.to_dict("records")}
            lines.append(f"| {kind} | {mode} | " + " | ".join(_cell(by[h], key) for h in HORIZON_NAMES) + " |")
        lines.append("")
    lines += ["## Trefferquote: Modell / Basisrate", "", "| Modell | Modus | " + " | ".join(HORIZON_NAMES) + " |",
              "|---|---|" + "---:|" * len(HORIZON_NAMES)]
    for (kind, mode), g in scores.groupby(["modell", "modus"], sort=False):
        by = {r["horizont"]: r for r in g.to_dict("records")}
        lines.append(f"| {kind} | {mode} | " + " | ".join(
            "–" if by[h]["n"] == 0 else f"{by[h]['treffer']:.1%} / {by[h]['basis_treffer']:.1%}" for h in HORIZON_NAMES) + " |")
    lines += ["", "## Unabhängige Fälle in den Testjahren", "", "| " + " | ".join(HORIZON_NAMES) + " |",
              "|" + "---:|" * len(HORIZON_NAMES),
              "| " + " | ".join(f"{int(first.loc[h, 'n_unabh'])}" for h in HORIZON_NAMES) + " |", ""]
    best = scores[scores.n > 0].groupby(["modell", "modus"], sort=False).pinball_skill.mean().idxmax()
    matrix = np.array(attentions[f"{best[0]}|{best[1]}"])
    lines += [f"## Welcher Timeframe zählt für welchen Horizont? ({best[0]}, {best[1]}, letztes Testjahr)", "",
              "Mittlere Attention je Horizont. Rund 14 % überall heißt: keine erkennbare Bevorzugung eines Timeframes.", "", "| Horizont | " + " | ".join(tfs) + " |", "|---|" + "---:|" * len(tfs)]
    for h, name in enumerate(HORIZON_NAMES):
        lines.append(f"| {name} | " + " | ".join(f"{v:.0%}" for v in matrix[h]) + " |")
    path = REPORTS / f"{symbol}_phase3.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

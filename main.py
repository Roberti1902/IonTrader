"""IonTrader: python main.py run | ingest | check | live | scan | universe | train | risk | matrix | finalcheck | pipeline | nightly | weekly, jeweils mit Ticker; snapshot fuer alle voll geprueften"""
import argparse
from datetime import datetime

from iontrader import ingest, live


def print_bar(bar):
    print(f"{datetime.fromtimestamp(bar['start']):%H:%M:%S}  O {bar['open']:.2f}  H {bar['high']:.2f}  "
          f"L {bar['low']:.2f}  C {bar['close']:.2f}  V {bar['volume']:,.0f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IonTrader")
    parser.add_argument("command", choices=["run", "ingest", "check", "live", "scan", "universe", "train", "risk", "matrix", "finalcheck", "pipeline", "nightly", "weekly", "snapshot", "backtest", "rank", "fundamentals"])
    parser.add_argument("ticker", nargs="?", default="META")
    parser.add_argument("--replay", nargs="?", type=float, const=5.0, metavar="SEKUNDEN", help="run: spielt den letzten Handelstag ab, SEKUNDEN je Minute")
    parser.add_argument("--no-browser", action="store_true", help="run: Browser nicht selbst oeffnen")
    parser.add_argument("--cached", action="store_true", help="rank: vorhandene Kurse nutzen statt neu zu laden")
    parser.add_argument("--push", action="store_true", help="snapshot: Seite danach zu GitHub hochladen")
    args = parser.parse_args()

    if args.command == "run":
        from iontrader import app

        app.run(args.ticker, args.replay, not args.no_browser)
    elif args.command in ("pipeline", "nightly", "weekly"):
        from iontrader import exit_now, pipeline

        ok = {"pipeline": pipeline.run, "nightly": pipeline.nightly, "weekly": pipeline.weekly}[args.command](args.ticker)
        print(f"{args.ticker.upper()}: {args.command} {'fertig' if ok else 'abgebrochen'}", flush=True)
        exit_now()
    elif args.command == "backtest":
        from iontrader import backtest, exit_now
        from iontrader.app import known_tickers

        backtest.run(known_tickers())
        exit_now()
    elif args.command == "fundamentals":
        from iontrader import exit_now, fundamentals

        fundamentals.run()
        exit_now()
    elif args.command == "rank":
        from iontrader import exit_now, ranking

        ranking.run(refresh=not args.cached)
        exit_now()
    elif args.command == "snapshot":
        from iontrader import exit_now, snapshot

        snapshot.build()
        if args.push:
            snapshot.push()
        exit_now()
    elif args.command == "ingest":
        print(f"{args.ticker.upper()}: Quelle fuer Intraday = {ingest.ingest(args.ticker)}")
        ingest.check(args.ticker)
    elif args.command == "check":
        ingest.check(args.ticker)
    elif args.command == "scan":
        from iontrader import features, study

        wall, cpu = features.run(args.ticker)
        study.run(args.ticker, wall=wall, cpu=cpu)
    elif args.command == "universe":
        from iontrader import universe

        universe.build()
    elif args.command == "train":
        from iontrader import dataset, exit_now, match, store, train

        train.tournament(args.ticker)
        con = store.connect()
        symbol = args.ticker.upper()
        folds, holdout = dataset.fold_dates(dataset.load_ticker(con, symbol))
        scores, timing = match.report(con, symbol, folds[0][0], holdout, train.REPORTS / f"{symbol}_phase3.md")
        print(f"Matching: {timing['sequenzen']:,} Sequenzen, Median {timing['ms_median']:.0f} ms je Abfrage", flush=True)
        exit_now()
    elif args.command == "risk":
        from iontrader import exit_now, risk

        risk.run(args.ticker)
        exit_now()
    elif args.command in ("matrix", "finalcheck"):
        from iontrader import exit_now, matrix

        (matrix.run_walk_forward if args.command == "matrix" else matrix.run_final)(args.ticker)
        exit_now()
    else:
        live.run(args.ticker, print_bar)

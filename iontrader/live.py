"""Live-Feed: einzelne Trades werden zu 5-Sekunden-Bars."""
import os
import threading
import time

import yfinance as yf


class Bars5s:
    """Sammelt Trades und meldet einen Bar, sobald der erste Trade des naechsten Fensters eintrifft."""

    def __init__(self, emit, seconds=5):
        self.emit, self.seconds, self.bar = emit, seconds, None

    def add(self, ts, price, size=0.0):
        start = int(ts // self.seconds) * self.seconds
        bar = self.bar
        if bar is None or bar["start"] != start:
            if bar is not None:
                self.emit(bar)
            self.bar = {"start": start, "open": price, "high": price, "low": price, "close": price, "volume": size}
            return
        bar["high"], bar["low"] = max(bar["high"], price), min(bar["low"], price)
        bar["close"] = price
        bar["volume"] += size


class AlpacaFeed:
    """Der freie Plan erlaubt nur eine Verbindung und Echtzeit nur von IEX. Beim Tickerwechsel wird deshalb umgemeldet."""

    def __init__(self, on_trade):
        from alpaca.data.live import StockDataStream

        self.symbol = None
        self.stream = StockDataStream(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])

        async def handler(trade):
            on_trade(trade.symbol.replace(".", "-"), trade.timestamp.timestamp(), trade.price, trade.size)

        self.handler = handler

    def watch(self, symbol):
        old, self.symbol = self.symbol, symbol.replace("-", ".")
        self.stream.subscribe_trades(self.handler, self.symbol)
        if old is None:
            threading.Thread(target=self.stream.run, daemon=True).start()
        elif old != self.symbol:
            self.stream.unsubscribe_trades(old)


class YahooFeed:
    def __init__(self, on_trade):
        self.on_trade, self.symbol, self.ws, self.day_volume = on_trade, None, None, None

    def _listen(self, first):
        with yf.WebSocket(verbose=False) as ws:
            self.ws = ws
            ws.subscribe(first)
            ws.listen(self._message)

    def _message(self, msg):
        volume = float(msg.get("day_volume") or 0)
        size = max(volume - self.day_volume, 0) if self.day_volume is not None else 0.0
        self.day_volume = volume
        self.on_trade(msg["id"], int(msg["time"]) / 1000, float(msg["price"]), size)

    def watch(self, symbol):
        old, self.symbol, self.day_volume = self.symbol, symbol, None
        if old is None:
            threading.Thread(target=self._listen, args=(symbol,), daemon=True).start()
        elif old != symbol and self.ws is not None:
            self.ws.unsubscribe(old)
            self.ws.subscribe(symbol)


def open_feed(on_trade):
    """on_trade(symbol, ts, price, size) laeuft im Feed-Thread."""
    return (AlpacaFeed if os.environ.get("ALPACA_API_KEY") else YahooFeed)(on_trade)


def replay(symbol, minutes, on_trade, seconds_per_bar=5.0, stop=None):
    """Spielt einen vergangenen Handelstag als Trades ab, damit sich der Live-Betrieb auch bei geschlossenem Markt pruefen laesst."""
    for row in minutes.itertuples():
        if stop is not None and stop.is_set():
            return
        end = row.Index.timestamp()
        # Vier Trades je Minute: Open, Extrem, Extrem, Close
        first, second = (row.low, row.high) if row.close >= row.open else (row.high, row.low)
        for offset, price in ((-59, row.open), (-40, first), (-20, second), (-1, row.close)):
            on_trade(symbol, end + offset, float(price), row.volume / 4)
            time.sleep(seconds_per_bar / 4)


def run(symbol, emit):
    """Blockiert und ruft emit(bar) fuer jeden fertigen 5-Sekunden-Bar auf."""
    symbol = symbol.upper()
    bars = Bars5s(emit)
    open_feed(lambda _, ts, price, size: bars.add(ts, price, size)).watch(symbol)
    threading.Event().wait()

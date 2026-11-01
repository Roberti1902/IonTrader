"""Phase 3: LSTM, GRU, Transformer und TFT. Je Timeframe ein Encoder, verbunden per Cross-Timeframe-Attention."""
import torch
import torch.nn.functional as F
from torch import nn

KINDS = ("lstm", "gru", "transformer", "tft")
TAUS = (0.1, 0.5, 0.9)


class RNNEncoder(nn.Module):
    def __init__(self, cell, d_in, d, dropout):
        super().__init__()
        self.proj = nn.Linear(d_in, d)
        self.rnn = cell(d, d, num_layers=2, batch_first=True, dropout=dropout)

    def forward(self, x):
        return self.rnn(F.gelu(self.proj(x)))[0][:, -1]


class TransformerEncoder(nn.Module):
    """Fasst Bars zu Patches zusammen; die neuesten Bars liegen immer im letzten Patch."""

    def __init__(self, d_in, d, window, dropout):
        super().__init__()
        self.patch = max(1, window // 16)
        self.tokens = window // self.patch
        self.embed = nn.Conv1d(d_in, d, kernel_size=self.patch, stride=self.patch)
        self.position = nn.Parameter(torch.zeros(1, self.tokens, d))
        layer = nn.TransformerEncoderLayer(d, 4, 2 * d, dropout, activation="gelu", batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)

    def forward(self, x):
        x = x[:, -self.tokens * self.patch:]
        return self.encoder(self.embed(x.transpose(1, 2)).transpose(1, 2) + self.position)[:, -1]


class GRN(nn.Module):
    """Gated Residual Network aus dem TFT-Paper von Lim et al."""

    def __init__(self, d_in, d, d_out=None, dropout=0.1):
        super().__init__()
        d_out = d_out or d
        self.fc1, self.fc2 = nn.Linear(d_in, d), nn.Linear(d, d_out)
        self.gate = nn.Linear(d_out, 2 * d_out)
        self.skip = nn.Linear(d_in, d_out) if d_in != d_out else nn.Identity()
        self.norm = nn.LayerNorm(d_out)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        h = self.dropout(self.fc2(F.elu(self.fc1(x))))
        return self.norm(self.skip(x) + F.glu(self.gate(h), dim=-1))


class TFTEncoder(nn.Module):
    """Variablenauswahl, lokales LSTM und Self-Attention."""

    # ponytail: Variablenauswahl ohne Einzel-Embedding je Variable, das braeuchte bei 100 Features und 126 Bars
    # mehrere GB je Batch; volle Variante, falls sich die Auswahl in Phase 5 als entscheidend erweist

    def __init__(self, d_in, d, dropout):
        super().__init__()
        self.select = GRN(d_in, d, d_in, dropout)
        self.proj = nn.Linear(d_in, d)
        self.lstm = nn.LSTM(d, d, batch_first=True)
        self.gate1, self.norm1 = nn.Linear(d, 2 * d), nn.LayerNorm(d)
        self.attention = nn.MultiheadAttention(d, 4, dropout=dropout, batch_first=True)
        self.gate2, self.norm2 = nn.Linear(d, 2 * d), nn.LayerNorm(d)
        self.out = GRN(d, d, dropout=dropout)

    def selection(self, x):
        return torch.softmax(self.select(x), dim=-1)

    def forward(self, x):
        v = self.proj(x * self.selection(x) * x.size(-1))
        h = self.norm1(F.glu(self.gate1(self.lstm(v)[0]), dim=-1) + v)
        a = self.attention(h, h, h, need_weights=False)[0]
        return self.out(self.norm2(F.glu(self.gate2(a), dim=-1) + h)[:, -1])


def make_encoder(kind, d_in, d, window, dropout):
    if kind == "lstm":
        return RNNEncoder(nn.LSTM, d_in, d, dropout)
    if kind == "gru":
        return RNNEncoder(nn.GRU, d_in, d, dropout)
    if kind == "transformer":
        return TransformerEncoder(d_in, d, window, dropout)
    if kind == "tft":
        return TFTEncoder(d_in, d, dropout)
    raise ValueError(f"Unbekannter Modelltyp: {kind}")


class IonNet(nn.Module):
    """Ein Horizont je Query, jede Query liest per Attention aus allen Timeframes.

    Die Ausgabe startet exakt auf der Basisrate und den Quantilen des Tickers aus den Trainingsdaten.
    Alles darueber hinaus muss das Netz aus den Daten lernen.
    """

    def __init__(self, kind, dims, windows, base_up, base_q, d=64, dropout=0.3):
        super().__init__()
        self.kind, self.tfs = kind, list(dims)
        self.encoders = nn.ModuleDict({tf: make_encoder(kind, dims[tf], d, windows[tf], dropout) for tf in self.tfs})
        self.tf_embed = nn.Parameter(torch.randn(len(self.tfs), d) * 0.02)
        n_tickers, n_horizons = base_up.shape
        self.query = nn.Parameter(torch.randn(n_horizons, d) * 0.02)
        self.ticker = nn.Embedding(n_tickers, d)
        nn.init.normal_(self.ticker.weight, std=0.02)
        self.cross = nn.MultiheadAttention(d, 4, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(d)
        self.heads = nn.ModuleList(
            nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Dropout(dropout), nn.Linear(d, 4)) for _ in range(n_horizons))
        for head in self.heads:
            nn.init.zeros_(head[-1].weight), nn.init.zeros_(head[-1].bias)
        p = base_up.clamp(0.01, 0.99)
        self.register_buffer("base_logit", torch.log(p / (1 - p)))
        self.register_buffer("base_mid", base_q[..., 1])
        self.register_buffer("base_down", _inv_softplus((base_q[..., 1] - base_q[..., 0]).clamp(min=1e-3)))
        self.register_buffer("base_up_gap", _inv_softplus((base_q[..., 2] - base_q[..., 1]).clamp(min=1e-3)))

    def forward(self, xs, ticker, attention=False):
        tokens = torch.stack([self.encoders[tf](xs[tf]) for tf in self.tfs], dim=1) + self.tf_embed
        queries = self.query.unsqueeze(0) + self.ticker(ticker).unsqueeze(1)
        mixed, weights = self.cross(queries, tokens, tokens, need_weights=attention)
        mixed = self.norm(mixed + queries)
        raw = torch.stack([head(mixed[:, i]) for i, head in enumerate(self.heads)], dim=1)
        logit = self.base_logit[ticker] + raw[..., 0]
        mid = self.base_mid[ticker] + raw[..., 2]
        low = mid - F.softplus(self.base_down[ticker] + raw[..., 1])
        high = mid + F.softplus(self.base_up_gap[ticker] + raw[..., 3])
        return logit, torch.stack([low, mid, high], dim=-1), weights


def _inv_softplus(x):
    return torch.log(torch.expm1(x))


def target_losses(logit, q, y, sigma, taus):
    """Je Beispiel und Horizont: Binary Cross Entropy der Richtung und Pinball der Spanne."""
    bce = F.binary_cross_entropy_with_logits(logit, (y > 0).float(), reduction="none")
    error = (y / sigma).unsqueeze(-1) - q
    return bce, torch.maximum(taus * error, (taus - 1) * error).mean(-1)


def loss_fn(logit, q, y, sigma, mask, taus, weights, base_logit, penalty=0.1):
    """Richtung plus Spanne, Horizonte gewichtet nach Zahl unabhaengiger Faelle.

    Die Strafe zieht die Richtung Richtung Basisrate: Abweichen muss sich lohnen.
    """
    bce, pinball = target_losses(logit, q, y, sigma, taus)
    per_horizon = ((bce + pinball + penalty * (logit - base_logit) ** 2) * mask).sum(0) / mask.sum(0).clamp(min=1)
    return (per_horizon * weights).sum() / weights.sum()

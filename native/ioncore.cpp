// ioncore: Rechenkern von IonTrader. Geht jeden Bar einzeln durch, nutzt alle CPU-Threads
// und sieht in jedem Schritt nur Daten bis zum aktuellen Bar.
#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/vector.h>
#include <omp.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

namespace nb = nanobind;
using In = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using InI = nb::ndarray<const int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

constexpr double NaN = std::numeric_limits<double>::quiet_NaN();

template <class T>
nb::ndarray<nb::numpy, T, nb::ndim<1>> to_numpy(std::vector<T>&& v) {
  auto* heap = new std::vector<T>(std::move(v));
  nb::capsule owner(heap, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
  return nb::ndarray<nb::numpy, T, nb::ndim<1>>(heap->data(), {heap->size()}, owner);
}

inline uint64_t splitmix64(uint64_t x) {
  x += 0x9E3779B97F4A7C15ULL;
  x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
  x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
  return x ^ (x >> 31);
}

// ---------------------------------------------------------------------------
// Scanner: Zigzag-Swings, Fibonacci und die 20 Muster aus dem Chart-Pattern-Bild
// ---------------------------------------------------------------------------

// Baerische Vorlagen. Die bullische Seite ist dieselbe Formel mit gespiegeltem Preis (sigma = -1), ID + 10.
enum Template { SKS, DOUBLE_TOP, TRIPLE_TOP, DESC_TRIANGLE, FLAG, PENNANT, WEDGE, RECTANGLE, INV_CUP, ROUND_TOP };

constexpr int ATR_N = 14;
constexpr double EQ_TOL = 0.15;        // "gleich hoch" = innerhalb 15 % der Musterhoehe
constexpr double SHOULDER_TOL = 0.35;  // Schultern duerfen staerker abweichen
constexpr double MAX_RETRACE = 0.66;   // Flagge, Wimpel, Keil korrigieren hoechstens so weit gegen die Fahnenstange
constexpr double PARALLEL_TOL = 0.35;  // Flagge: Kanalsteigungen weichen hoechstens so weit ab, sonst Keil
constexpr int64_t MIN_CUP_BARS = 15;
constexpr int64_t MIN_ROUND_BARS = 20;

struct Swing {
  int64_t bar, confirm;  // Extrem-Bar und Bar, ab dem der Swing bekannt ist
  double price;
  int type;  // +1 Hoch, -1 Tief
};

struct Pending {
  int pattern, sigma;
  int64_t start, expire;
  double a, b, sl, measure, invalid;  // Trigger-Linie a + b*i; alle Werte in der Sigma-Welt
  bool round_at_trigger;
};

struct Event {
  int pattern;
  int64_t bar, start;
  double entry, sl, tp;
  int side;
};

class Scanner {
 public:
  Scanner(const double* h, const double* l, const double* c, int64_t n, double k)
      : h(h), l(l), c(c), n(n), k(k), fib_ret(n, NaN), fib_dir(n, NaN), fib_near(n, NaN), fib_382(n, NaN),
        fib_618(n, NaN), leg_atr(n, NaN), since(n, NaN), trend(n, NaN) {
    std::fill(std::begin(last_fire), std::end(last_fire), int64_t{-1});
  }

  void run() {
    for (int64_t i = 0; i < n; ++i) {
      update_atr(i);
      const size_t before = sw.size();
      update_zigzag(i);
      if (sw.size() != before) register_patterns();
      check_pending(i);
      write_features(i);
    }
  }

  std::vector<Swing> sw;
  std::vector<Event> ev;
  std::vector<double> fib_ret, fib_dir, fib_near, fib_382, fib_618, leg_atr, since, trend;

 private:
  const double* h;
  const double* l;
  const double* c;
  int64_t n;
  double k;
  double atr = 0, hi = -1e300, lo = 1e300, cand = 0;
  int64_t hi_bar = 0, lo_bar = 0, cand_bar = 0;
  int dir = 0;
  std::vector<Pending> pend;
  int64_t last_fire[20];

  void update_atr(int64_t i) {
    const double tr = i == 0 ? h[0] - l[0]
                             : std::max({h[i] - l[i], std::fabs(h[i] - c[i - 1]), std::fabs(l[i] - c[i - 1])});
    atr = i < ATR_N ? (atr * i + tr) / (i + 1) : (atr * (ATR_N - 1) + tr) / ATR_N;
  }

  void update_zigzag(int64_t i) {
    const double need = k * atr;
    if (need <= 0) return;
    if (dir == 0) {
      if (h[i] > hi) hi = h[i], hi_bar = i;
      if (l[i] < lo) lo = l[i], lo_bar = i;
      if (hi - lo >= need) {
        if (hi_bar > lo_bar) {
          sw.push_back({lo_bar, i, lo, -1});
          dir = 1, cand = hi, cand_bar = hi_bar;
        } else {
          sw.push_back({hi_bar, i, hi, 1});
          dir = -1, cand = lo, cand_bar = lo_bar;
        }
      }
    } else if (dir == 1) {
      if (h[i] > cand) {
        cand = h[i], cand_bar = i;
      } else if (cand - l[i] >= need) {
        sw.push_back({cand_bar, i, cand, 1});
        dir = -1, cand = l[i], cand_bar = i;
      }
    } else {
      if (l[i] < cand) {
        cand = l[i], cand_bar = i;
      } else if (h[i] - cand >= need) {
        sw.push_back({cand_bar, i, cand, -1});
        dir = 1, cand = h[i], cand_bar = i;
      }
    }
  }

  void add(int pattern, int sigma, int64_t start, double a, double b, double sl, double measure, double invalid,
           int64_t expire, bool round = false) {
    pend.push_back({pattern, sigma, start, expire, a, b, sl, measure, invalid, round});
  }

  // Parabel-Fit auf sigma*close: Kappe (nach unten offen), passt gut, Scheitel im mittleren Teil
  bool rounded(int64_t from, int64_t to, int sigma, double min_r2) const {
    const int64_t len = to - from + 1;
    const int64_t step = std::max<int64_t>(1, len / 256);
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0, t0 = 0, t1 = 0, t2 = 0, yy = 0;
    const double base = sigma * c[from];
    for (int64_t j = from; j <= to; j += step) {
      const double x = double(j - from) / (len - 1), y = sigma * c[j] - base, x2 = x * x;
      s0 += 1, s1 += x, s2 += x2, s3 += x2 * x, s4 += x2 * x2;
      t0 += y, t1 += x * y, t2 += x2 * y, yy += y * y;
    }
    const double det = s0 * (s2 * s4 - s3 * s3) - s1 * (s1 * s4 - s3 * s2) + s2 * (s1 * s3 - s2 * s2);
    if (std::fabs(det) < 1e-12) return false;
    const double c0 = (t0 * (s2 * s4 - s3 * s3) - s1 * (t1 * s4 - s3 * t2) + s2 * (t1 * s3 - s2 * t2)) / det;
    const double c1 = (s0 * (t1 * s4 - s3 * t2) - t0 * (s1 * s4 - s3 * s2) + s2 * (s1 * t2 - t1 * s2)) / det;
    const double c2 = (s0 * (s2 * t2 - t1 * s3) - s1 * (s1 * t2 - t1 * s2) + t0 * (s1 * s3 - s2 * s2)) / det;
    const double tss = yy - t0 * t0 / s0, rss = yy - (c0 * t0 + c1 * t1 + c2 * t2);
    if (c2 >= 0 || tss <= 0 || 1 - rss / tss < min_r2) return false;
    const double vertex = -c1 / (2 * c2);
    return vertex >= 0.25 && vertex <= 0.75;
  }

  void register_patterns() {
    const int64_t m = static_cast<int64_t>(sw.size());
    for (int sigma : {1, -1}) {
      auto v = [&](int j) { return sigma * sw[m - j].price; };
      auto b = [&](int j) { return sw[m - j].bar; };

      if (sigma * sw.back().type == -1) {  // letzter Swing ist ein Tief: Absteigendes Dreieck
        if (m >= 4) {
          const double H1 = v(4), L2 = v(3), H3 = v(2), L4 = v(1);
          const double floor_ = std::min(L2, L4), height = H1 - floor_;
          if (height > 0 && H1 - H3 >= 0.1 * height && H3 > floor_ + 0.2 * height &&
              std::fabs(L2 - L4) <= EQ_TOL * height)
            add(DESC_TRIANGLE, sigma, b(4), floor_, 0, H3, height, H3, b(1) + (b(1) - b(4)) / 2);
        }
        continue;
      }

      bool triple = false;
      if (m >= 6) {
        const double L0 = v(6), H1 = v(5), L2 = v(4), H3 = v(3), L4 = v(2), H5 = v(1);
        // Schulter-Kopf-Schulter: SL an der rechten Schulter, TP = Kopfhoehe ueber der Nackenlinie
        const double slope = (L4 - L2) / double(b(2) - b(4));
        const double height = H3 - (L2 + slope * double(b(3) - b(4)));
        const int64_t left = b(3) - b(5), right = b(1) - b(3);
        if (H3 > std::max(H1, H5) && std::min(H1, H5) > std::max(L2, L4) && height > 0 &&
            std::fabs(H1 - H5) <= SHOULDER_TOL * height && L0 < std::min(L2, L4) &&
            std::max(left, right) <= 3 * std::min(left, right))
          add(SKS, sigma, b(5), L2 - slope * b(4), slope, H5, height, H5, b(1) + (b(1) - b(5)));
        // Dreifachtop: SL an der oberen Linie, TP = Hoehe
        const double top = std::max({H1, H3, H5}), neck = std::min(L2, L4), h3 = top - neck;
        if (h3 > 0 && std::min({H1, H3, H5}) >= top - EQ_TOL * h3 && std::fabs(L2 - L4) <= EQ_TOL * h3 && L0 < neck) {
          triple = true;
          add(TRIPLE_TOP, sigma, b(5), neck, 0, top, h3, top, b(1) + (b(1) - b(5)) / 2);
        }
      }
      if (m >= 4) {
        const double A = v(4), B = v(3), C = v(2), D = v(1);
        // Doppeltop: SL am Hoch, TP = Hoehe
        const double top = std::max(B, D), height = top - C;
        if (!triple && height > 0 && std::fabs(B - D) <= EQ_TOL * height && A < C)
          add(DOUBLE_TOP, sigma, b(3), C, 0, top, height, top, b(1) + (b(1) - b(3)));
        // Inverse Tasse mit Henkel: SL am Henkel, TP = Tassentiefe
        const double depth = B - std::max(A, C);
        const int64_t cup = b(2) - b(4), handle = b(1) - b(2);
        if (depth > 0 && std::fabs(A - C) <= EQ_TOL * depth && D < B && D - C <= 0.5 * depth && cup >= MIN_CUP_BARS &&
            handle <= cup / 2 && rounded(b(4), b(2), sigma, 0.7))
          add(INV_CUP, sigma, b(4), C, 0, D, depth, D, b(1) + std::max(2 * handle, cup / 4));
      }
      if (m >= 5) {
        const double H0 = v(5), L1 = v(4), H2 = v(3), L3 = v(2), H4 = v(1);
        const double top = std::max(H2, H4), bottom = std::min(L1, L3), height = top - bottom, pole = H0 - L1;
        const int64_t pole_bars = b(4) - b(5), body = b(1) - b(4);
        const int64_t expire = b(1) + std::max<int64_t>(5, body / 2);
        const double line = (L3 - L1) / double(b(2) - b(4));
        const double a = L1 - line * b(4);
        if (height > 0 && std::fabs(H2 - H4) <= EQ_TOL * height && std::fabs(L1 - L3) <= EQ_TOL * height &&
            H0 - top >= height) {
          // Baerisches Rechteck nach einem Abverkauf: SL an der oberen Linie, TP = Hoehe
          add(RECTANGLE, sigma, b(4), bottom, 0, top, height, top, expire);
        } else if (pole > 0 && L3 > L1 && top - L1 <= MAX_RETRACE * pole && body <= 4 * pole_bars) {
          const double slope_high = (H4 - H2) / double(b(1) - b(3)), slope_low = line;
          if (H4 < H2) {  // Wimpel: Linien laufen zusammen, TP = groesste Breite
            add(PENNANT, sigma, b(5), a, line, H4, top - L1, H4, expire);
          } else if (std::fabs(slope_high - slope_low) <= PARALLEL_TOL * std::max(slope_high, slope_low)) {
            add(FLAG, sigma, b(5), a, line, H4, pole, H4, expire);  // Flagge: TP = Fahnenstange
          } else if (slope_low > slope_high) {                      // Keil: steigend und zusammenlaufend
            add(WEDGE, sigma, b(5), a, line, H4, top - L1, H4, expire);
          }
        }
      }
      if (m >= 2) {
        // Rounding Top: SL auf Scheitelhoehe, TP = Hoehe. Die Form wird erst beim Ausbruch geprueft.
        const double rim = v(2), peak = v(1);
        if (peak > rim)
          add(ROUND_TOP, sigma, b(2), rim, 0, peak, peak - rim, peak, b(1) + (b(1) - b(2)) * 3 / 2, true);
      }
    }
  }

  void check_pending(int64_t i) {
    for (size_t j = 0; j < pend.size();) {
      const Pending& p = pend[j];
      const double px = p.sigma * c[i];
      const double level = p.a + p.b * i;
      bool drop = i > p.expire || px > p.invalid;
      if (!drop && px < level) {
        drop = true;
        const double tp = level - p.measure;
        const int id = p.pattern + (p.sigma == 1 ? 0 : 10);
        const bool shape_ok = !p.round_at_trigger ||
                              (i - p.start >= MIN_ROUND_BARS && rounded(p.start, i, p.sigma, 0.75));
        if (px > tp && p.sl > px && shape_ok && last_fire[id] != i) {
          last_fire[id] = i;
          ev.push_back({id, i, p.start, c[i], p.sigma * p.sl, p.sigma * tp, -p.sigma});
        }
      }
      if (drop) {
        pend[j] = pend.back();
        pend.pop_back();
      } else {
        ++j;
      }
    }
  }

  void write_features(int64_t i) {
    const size_t m = sw.size();
    if (m < 2 || atr <= 0) return;
    static constexpr double levels[] = {0.236, 0.382, 0.5, 0.618, 0.786, 1.272, 1.618};
    const double A = sw[m - 2].price, B = sw[m - 1].price, leg = B - A;
    fib_ret[i] = (B - c[i]) / leg;  // 0 = am letzten Swing, 1 = komplett zurueck zum vorherigen
    fib_dir[i] = leg > 0 ? 1 : -1;
    double near = 1e300;
    for (double r : levels) near = std::min(near, std::fabs(c[i] - (B - r * leg)));
    fib_near[i] = near / atr;
    fib_382[i] = (c[i] - (B - 0.382 * leg)) / atr;
    fib_618[i] = (c[i] - (B - 0.618 * leg)) / atr;
    leg_atr[i] = std::fabs(leg) / atr;
    since[i] = double(i - sw[m - 1].bar);
    if (m >= 4) {  // Struktur: hoehere Hochs und Tiefs = +1, tiefere = -1
      const double step1 = sw[m - 1].price - sw[m - 3].price, step2 = sw[m - 2].price - sw[m - 4].price;
      trend[i] = (step1 > 0 && step2 > 0) ? 1 : (step1 < 0 && step2 < 0) ? -1 : 0;
    }
  }
};

nb::list scan(In h, In l, In c, const std::vector<double>& ks) {
  const int64_t n = static_cast<int64_t>(c.shape(0));
  if (static_cast<int64_t>(h.shape(0)) != n || static_cast<int64_t>(l.shape(0)) != n)
    throw std::invalid_argument("high, low und close muessen gleich lang sein");
  std::vector<Scanner> scanners;
  scanners.reserve(ks.size());
  for (double k : ks) scanners.emplace_back(h.data(), l.data(), c.data(), n, k);
  {
    nb::gil_scoped_release release;
    const int64_t count = static_cast<int64_t>(scanners.size());
#pragma omp parallel for schedule(dynamic)
    for (int64_t j = 0; j < count; ++j) scanners[j].run();
  }
  nb::list out;
  for (auto& s : scanners) {
    std::vector<int64_t> pattern, bar, start, side, sw_bar, sw_confirm, sw_type;
    std::vector<double> entry, sl, tp, sw_price;
    for (const Event& e : s.ev) {
      pattern.push_back(e.pattern), bar.push_back(e.bar), start.push_back(e.start), side.push_back(e.side);
      entry.push_back(e.entry), sl.push_back(e.sl), tp.push_back(e.tp);
    }
    for (const Swing& w : s.sw) {
      sw_bar.push_back(w.bar), sw_confirm.push_back(w.confirm), sw_type.push_back(w.type), sw_price.push_back(w.price);
    }
    nb::dict d;
    d["pattern"] = to_numpy(std::move(pattern));
    d["bar"] = to_numpy(std::move(bar));
    d["start"] = to_numpy(std::move(start));
    d["side"] = to_numpy(std::move(side));
    d["entry"] = to_numpy(std::move(entry));
    d["sl"] = to_numpy(std::move(sl));
    d["tp"] = to_numpy(std::move(tp));
    d["swing_bar"] = to_numpy(std::move(sw_bar));
    d["swing_confirm"] = to_numpy(std::move(sw_confirm));
    d["swing_type"] = to_numpy(std::move(sw_type));
    d["swing_price"] = to_numpy(std::move(sw_price));
    d["fib_ret"] = to_numpy(std::move(s.fib_ret));
    d["fib_dir"] = to_numpy(std::move(s.fib_dir));
    d["fib_near"] = to_numpy(std::move(s.fib_near));
    d["fib_382"] = to_numpy(std::move(s.fib_382));
    d["fib_618"] = to_numpy(std::move(s.fib_618));
    d["leg_atr"] = to_numpy(std::move(s.leg_atr));
    d["since"] = to_numpy(std::move(s.since));
    d["trend"] = to_numpy(std::move(s.trend));
    out.append(d);
  }
  return out;
}

struct Walk {
  int64_t outcome, bars;
  double r;
};

// Was wurde zuerst getroffen: TP (+1), SL (-1), Zeitlimit (0). Ende der Daten ohne Ausgang: -2.
// Fallen TP und SL in denselben Bar, zaehlt konservativ der SL.
inline Walk walk_barriers(const double* h, const double* l, const double* c, int64_t n, int64_t t0, int64_t side,
                          double sl, double tp, int64_t max_bars) {
  const int64_t last = t0 + max_bars;
  const double entry = c[t0], risk = std::fabs(entry - sl);
  for (int64_t t = t0 + 1; t <= last && t < n; ++t) {
    const bool hit_sl = side > 0 ? l[t] <= sl : h[t] >= sl;
    const bool hit_tp = side > 0 ? h[t] >= tp : l[t] <= tp;
    if (hit_sl || hit_tp) return {hit_sl ? -1 : 1, t - t0, (hit_sl ? sl - entry : tp - entry) * side / risk};
    if (t == last) return {0, t - t0, (c[t] - entry) * side / risk};
  }
  return {-2, 0, NaN};
}

nb::dict triple_barrier(In h_, In l_, In c_, InI bar_, InI side_, In sl_, In tp_, InI max_bars_) {
  const int64_t n = static_cast<int64_t>(c_.shape(0)), m = static_cast<int64_t>(bar_.shape(0));
  const double* h = h_.data();
  const double* l = l_.data();
  const double* c = c_.data();
  const int64_t* bar = bar_.data();
  const int64_t* side = side_.data();
  const double* sl = sl_.data();
  const double* tp = tp_.data();
  const int64_t* max_bars = max_bars_.data();
  std::vector<int64_t> outcome(m, -2), bars(m, 0);
  std::vector<double> r(m, NaN);
  {
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(dynamic, 64)
    for (int64_t e = 0; e < m; ++e) {
      const Walk w = walk_barriers(h, l, c, n, bar[e], side[e], sl[e], tp[e], max_bars[e]);
      outcome[e] = w.outcome, bars[e] = w.bars, r[e] = w.r;
    }
  }
  nb::dict d;
  d["outcome"] = to_numpy(std::move(outcome));
  d["bars"] = to_numpy(std::move(bars));
  d["r"] = to_numpy(std::move(r));
  return d;
}

// Kontrollgruppe: gleiche Richtung, gleiche SL/TP-Abstaende in ATR und gleiches Zeitlimit, aber an gemeinsam
// verschobenen Zeitpunkten. Trennt das, was das Muster leistet, vom Grundtrend der Aktie. Zweiseitiger p-Wert.
nb::tuple control_test(In h_, In l_, In c_, In atr_, InI bar_, InI side_, In sl_atr_, In tp_atr_, InI max_bars_,
                       int64_t n_shift, uint64_t seed) {
  const int64_t n = static_cast<int64_t>(c_.shape(0)), m = static_cast<int64_t>(bar_.shape(0));
  if (m == 0 || n < 2) return nb::make_tuple(NaN, NaN, NaN);
  const double* h = h_.data();
  const double* l = l_.data();
  const double* c = c_.data();
  const double* atr = atr_.data();
  const int64_t* bar = bar_.data();
  const int64_t* side = side_.data();
  const double* sl_atr = sl_atr_.data();
  const double* tp_atr = tp_atr_.data();
  const int64_t* max_bars = max_bars_.data();
  auto mean_r = [&](int64_t offset) {
    double sum = 0;
    int64_t count = 0;
    for (int64_t e = 0; e < m; ++e) {
      int64_t t0 = bar[e] + offset;
      if (t0 >= n) t0 -= n;
      const double a = atr[t0];
      if (!(a > 0)) continue;
      const double entry = c[t0];
      const double r = walk_barriers(h, l, c, n, t0, side[e], entry + sl_atr[e] * a, entry + tp_atr[e] * a, max_bars[e]).r;
      if (std::isfinite(r)) sum += r, ++count;
    }
    return count ? sum / count : NaN;
  };
  double real = NaN, control = 0, p = NaN;
  {
    nb::gil_scoped_release release;
    real = mean_r(0);
    std::vector<double> means(n_shift);
#pragma omp parallel for schedule(dynamic, 16)
    for (int64_t s = 0; s < n_shift; ++s)
      means[s] = mean_r(1 + static_cast<int64_t>(splitmix64(seed + s) % uint64_t(n - 1)));
    int64_t used = 0, beyond = 0;
    for (double v : means)
      if (std::isfinite(v)) control += v, ++used;
    control = used ? control / used : NaN;
    for (double v : means)
      if (std::isfinite(v) && std::fabs(v - control) >= std::fabs(real - control)) ++beyond;
    p = used ? double(1 + beyond) / double(1 + used) : NaN;
  }
  return nb::make_tuple(real, control, p);
}

// ---------------------------------------------------------------------------
// Fraktal: rollende Multifraktale DFA fuer jeden Bar
// ---------------------------------------------------------------------------

std::vector<int64_t> dfa_scales(int64_t window) {
  std::vector<int64_t> scales;
  const double lo = 8, hi = window / 4.0;
  const int count = 9;
  for (int i = 0; i < count && hi >= lo; ++i) {
    const int64_t s = std::llround(lo * std::pow(hi / lo, count > 1 ? double(i) / (count - 1) : 0));
    if (scales.empty() || s != scales.back()) scales.push_back(s);
  }
  return scales;
}

double slope(const std::vector<double>& x, const std::vector<double>& y, int used) {
  if (used < 3) return NaN;
  double mx = 0, my = 0;
  for (int i = 0; i < used; ++i) mx += x[i], my += y[i];
  mx /= used, my /= used;
  double sxy = 0, sxx = 0;
  for (int i = 0; i < used; ++i) sxy += (x[i] - mx) * (y[i] - my), sxx += (x[i] - mx) * (x[i] - mx);
  return sxy / sxx;
}

// h2 = Hurst-Schaetzer (q = 2), dh = h(-2) - h(2) als Breite des Multifraktal-Spektrums
nb::dict rolling_mfdfa(In x_, int64_t window) {
  const int64_t n = static_cast<int64_t>(x_.shape(0));
  const double* x = x_.data();
  std::vector<double> h2(n, NaN), dh(n, NaN);
  const std::vector<int64_t> scales = dfa_scales(window);
  const int ns = static_cast<int>(scales.size());
  if (n >= window && ns >= 3) {
    nb::gil_scoped_release release;
#pragma omp parallel
    {
      std::vector<double> y(window), ls(ns), f2(ns), fm2(ns), ls2(ns), lsm(ns);
#pragma omp for schedule(static, 512)
      for (int64_t t = window - 1; t < n; ++t) {
        const double* w = x + t - window + 1;
        double mean = 0;
        for (int64_t j = 0; j < window; ++j) mean += w[j];
        mean /= window;
        double cum = 0;
        for (int64_t j = 0; j < window; ++j) {
          cum += w[j] - mean;
          y[j] = cum;
        }
        int used = 0;
        for (int si = 0; si < ns; ++si) {
          const int64_t s = scales[si], nseg = window / s;
          const double xbar = (s - 1) / 2.0, sxx = s * (double(s) * s - 1) / 12.0;
          double m2 = 0, mm2 = 0;
          int64_t cnt = 0;
          for (int64_t seg = 0; seg < nseg; ++seg) {
            const double* q = y.data() + seg * s;
            double sy = 0, sxy = 0, syy = 0;
            for (int64_t j = 0; j < s; ++j) {
              sy += q[j];
              sxy += (j - xbar) * q[j];
              syy += q[j] * q[j];
            }
            const double f = (syy - sy * sy / s - sxy * sxy / sxx) / s;
            if (f > 1e-30) m2 += f, mm2 += 1 / f, ++cnt;
          }
          if (cnt > 0) {
            ls[used] = std::log(double(s));
            f2[used] = 0.5 * std::log(m2 / cnt);
            fm2[used] = -0.5 * std::log(mm2 / cnt);
            ++used;
          }
        }
        const double a2 = slope(ls, f2, used);
        h2[t] = a2;
        dh[t] = slope(ls, fm2, used) - a2;
      }
    }
  }
  nb::dict d;
  d["h2"] = to_numpy(std::move(h2));
  d["dh"] = to_numpy(std::move(dh));
  return d;
}

// ---------------------------------------------------------------------------
// Mean Reversion: rollender ADF-Test, Halbwertszeit und Variance Ratio
// ---------------------------------------------------------------------------

nb::dict rolling_mr(In close_, int64_t window) {
  const int64_t n = static_cast<int64_t>(close_.shape(0));
  std::vector<double> p(n), adf(n, NaN), half_life(n, NaN), vr2(n, NaN), vr4(n, NaN), vr8(n, NaN);
  for (int64_t i = 0; i < n; ++i) p[i] = std::log(close_.data()[i]);
  if (n > window && window >= 32) {
    nb::gil_scoped_release release;
#pragma omp parallel for schedule(static, 512)
    for (int64_t t = window; t < n; ++t) {
      const double* w = p.data() + t - window;  // window + 1 Punkte
      // ADF mit einem Lag: dp[j] = c + beta * p[j-1] + gamma * dp[j-1]
      double s11 = 0, s12 = 0, s13 = 0, s22 = 0, s23 = 0, s33 = 0, t1 = 0, t2 = 0, t3 = 0, yy = 0;
      const double base = w[0];
      for (int64_t j = 2; j <= window; ++j) {
        const double y = w[j] - w[j - 1], x2 = w[j - 1] - base, x3 = w[j - 1] - w[j - 2];
        s11 += 1, s12 += x2, s13 += x3, s22 += x2 * x2, s23 += x2 * x3, s33 += x3 * x3;
        t1 += y, t2 += x2 * y, t3 += x3 * y, yy += y * y;
      }
      const double c11 = s22 * s33 - s23 * s23, c12 = s13 * s23 - s12 * s33, c13 = s12 * s23 - s13 * s22;
      const double det = s11 * c11 + s12 * c12 + s13 * c13;
      if (std::fabs(det) > 1e-20) {
        const double c22 = s11 * s33 - s13 * s13, c23 = s12 * s13 - s11 * s23, c33 = s11 * s22 - s12 * s12;
        const double b1 = (c11 * t1 + c12 * t2 + c13 * t3) / det;
        const double b2 = (c12 * t1 + c22 * t2 + c23 * t3) / det;
        const double b3 = (c13 * t1 + c23 * t2 + c33 * t3) / det;
        const double dof = double(window - 1 - 3);
        const double s2 = (yy - b1 * t1 - b2 * t2 - b3 * t3) / dof;
        const double var_b = s2 * c22 / det;
        if (var_b > 0) adf[t] = b2 / std::sqrt(var_b);
        if (b2 < 0 && b2 > -1) half_life[t] = -std::log(2.0) / std::log(1 + b2);
      }
      // Variance Ratio: < 1 kehrt um, > 1 haelt an
      const double mu = (w[window] - w[0]) / window;
      double var1 = 0;
      for (int64_t j = 1; j <= window; ++j) {
        const double e = w[j] - w[j - 1] - mu;
        var1 += e * e;
      }
      var1 /= window - 1;
      if (var1 > 0) {
        for (int q : {2, 4, 8}) {
          double var_q = 0;
          for (int64_t j = q; j <= window; ++j) {
            const double e = w[j] - w[j - q] - q * mu;
            var_q += e * e;
          }
          var_q /= double(window - q + 1) * q;
          (q == 2 ? vr2 : q == 4 ? vr4 : vr8)[t] = var_q / var1;
        }
      }
    }
  }
  nb::dict d;
  d["adf"] = to_numpy(std::move(adf));
  d["half_life"] = to_numpy(std::move(half_life));
  d["vr2"] = to_numpy(std::move(vr2));
  d["vr4"] = to_numpy(std::move(vr4));
  d["vr8"] = to_numpy(std::move(vr8));
  return d;
}

// ---------------------------------------------------------------------------
// Signifikanz: Zirkular-Shift-Test. Verschiebt alle Ereignisse gemeinsam und erhaelt so
// ihre Haeufung und die Ueberlappung der Renditen. Zweiseitig gegen den Mittelwert aller Bars.
// ---------------------------------------------------------------------------

nb::tuple shift_test(In fwd_, InI events_, int64_t n_shift, uint64_t seed) {
  const int64_t n = static_cast<int64_t>(fwd_.shape(0));
  std::vector<int64_t> pos(n, -1);
  std::vector<double> y;
  y.reserve(n);
  for (int64_t i = 0; i < n; ++i) {
    if (std::isfinite(fwd_.data()[i])) {
      pos[i] = static_cast<int64_t>(y.size());
      y.push_back(fwd_.data()[i]);
    }
  }
  std::vector<int64_t> ev;
  for (size_t i = 0; i < events_.shape(0); ++i) {
    const int64_t e = events_.data()[i];
    if (e >= 0 && e < n && pos[e] >= 0) ev.push_back(pos[e]);
  }
  const int64_t m = static_cast<int64_t>(y.size()), k = static_cast<int64_t>(ev.size());
  if (k == 0 || m < 2) return nb::make_tuple(NaN, NaN, NaN, k);
  double all = 0, mean_ev = 0;
  for (double v : y) all += v;
  all /= m;
  for (int64_t e : ev) mean_ev += y[e];
  mean_ev /= k;
  const double dev = std::fabs(mean_ev - all);
  int64_t count = 0;
  {
    nb::gil_scoped_release release;
#pragma omp parallel for reduction(+ : count) schedule(static)
    for (int64_t s = 0; s < n_shift; ++s) {
      const int64_t offset = 1 + static_cast<int64_t>(splitmix64(seed + s) % uint64_t(m - 1));
      double sum = 0;
      for (int64_t j = 0; j < k; ++j) {
        int64_t idx = ev[j] + offset;
        if (idx >= m) idx -= m;
        sum += y[idx];
      }
      if (std::fabs(sum / k - all) >= dev) ++count;
    }
  }
  return nb::make_tuple(mean_ev, all, double(1 + count) / double(1 + n_shift), k);
}

// ---------------------------------------------------------------------------
// Pattern-Matching: jedes Fenster auf gleiche Laenge und Einheitsnorm bringen, damit
// Formen ueber Timeframes und Fensterlaengen hinweg direkt vergleichbar sind
// ---------------------------------------------------------------------------

nb::ndarray<nb::numpy, float, nb::ndim<2>> make_windows(In x_, int64_t window, int64_t length) {
  if (window < 2 || length < 2) throw std::invalid_argument("window und length muessen mindestens 2 sein");
  const int64_t n = static_cast<int64_t>(x_.shape(0));
  const int64_t rows = std::max<int64_t>(0, n - window + 1);
  const double* x = x_.data();
  auto* heap = new std::vector<float>(rows * length);
  float* out = heap->data();
  {
    nb::gil_scoped_release release;
#pragma omp parallel
    {
      std::vector<double> buf(length);
#pragma omp for schedule(static, 4096)
      for (int64_t r = 0; r < rows; ++r) {
        const double* w = x + r;
        double mean = 0;
        for (int64_t j = 0; j < length; ++j) {
          const double pos = double(j) * (window - 1) / (length - 1);
          const int64_t i = std::min<int64_t>(static_cast<int64_t>(pos), window - 2);
          const double frac = pos - i;
          buf[j] = w[i] * (1 - frac) + w[i + 1] * frac;
          mean += buf[j];
        }
        mean /= length;
        double norm = 0;
        for (int64_t j = 0; j < length; ++j) {
          buf[j] -= mean;
          norm += buf[j] * buf[j];
        }
        norm = std::sqrt(norm);
        // Ein flaches Fenster hat keine Form und bekommt Nullen, also Aehnlichkeit 0 zu allem
        for (int64_t j = 0; j < length; ++j) out[r * length + j] = norm > 1e-12 ? float(buf[j] / norm) : 0.0f;
      }
    }
  }
  nb::capsule owner(heap, [](void* p) noexcept { delete static_cast<std::vector<float>*>(p); });
  return nb::ndarray<nb::numpy, float, nb::ndim<2>>(out, {size_t(rows), size_t(length)}, owner);
}

// Feinvergleich der besten Kandidaten: erlaubt leichte zeitliche Verschiebung innerhalb des Bands
nb::ndarray<nb::numpy, double, nb::ndim<1>> dtw(nb::ndarray<const float, nb::ndim<1>, nb::c_contig, nb::device::cpu> query_,
                                               nb::ndarray<const float, nb::ndim<2>, nb::c_contig, nb::device::cpu> cands_,
                                               int64_t band) {
  const int64_t len = static_cast<int64_t>(query_.shape(0)), m = static_cast<int64_t>(cands_.shape(0));
  if (static_cast<int64_t>(cands_.shape(1)) != len) throw std::invalid_argument("Kandidaten und Abfrage muessen gleich lang sein");
  const float* q = query_.data();
  const float* c = cands_.data();
  std::vector<double> out(m);
  {
    nb::gil_scoped_release release;
#pragma omp parallel
    {
      constexpr double INF = std::numeric_limits<double>::infinity();
      std::vector<double> prev(len + 1), cur(len + 1);
#pragma omp for schedule(static)
      for (int64_t e = 0; e < m; ++e) {
        const float* row = c + e * len;
        std::fill(prev.begin(), prev.end(), INF);
        prev[0] = 0;
        for (int64_t i = 1; i <= len; ++i) {
          std::fill(cur.begin(), cur.end(), INF);
          const int64_t from = std::max<int64_t>(1, i - band), to = std::min(len, i + band);
          for (int64_t j = from; j <= to; ++j) {
            const double d = q[i - 1] - row[j - 1];
            cur[j] = d * d + std::min({prev[j], cur[j - 1], prev[j - 1]});
          }
          std::swap(prev, cur);
        }
        out[e] = std::sqrt(prev[len]);
      }
    }
  }
  return to_numpy(std::move(out));
}

// ---------------------------------------------------------------------------
// Risiko: GJR-GARCH(1,1) mit Variance Targeting. Negative Schocks duerfen die Schwankung staerker erhoehen.
// sigma2[t+1] = omega + (alpha + gamma * (e[t] < 0)) * e[t]^2 + beta * sigma2[t]
// ---------------------------------------------------------------------------

double gjr_nll(const double* e, int64_t n, double a, double g, double b, double var) {
  constexpr double INF = std::numeric_limits<double>::infinity();
  if (a < 0 || g < 0 || b < 0 || a + 0.5 * g + b >= 0.999) return INF;
  const double omega = var * (1 - a - 0.5 * g - b);
  double s2 = var, nll = 0;
  for (int64_t t = 0; t < n; ++t) {
    const double e2 = e[t] * e[t];
    nll += std::log(s2) + e2 / s2;
    s2 = omega + (a + (e[t] < 0 ? g : 0.0)) * e2 + b * s2;
  }
  return 0.5 * nll;
}

// Nelder-Mead in drei Dimensionen, ohne Abhaengigkeit von einer Optimierungs-Bibliothek
template <class F>
double nelder_mead(F f, std::array<double, 3>& x, double step, int iterations) {
  std::array<std::array<double, 3>, 4> p;
  std::array<double, 4> v;
  p[0] = x;
  for (int i = 0; i < 3; ++i) {
    p[i + 1] = x;
    p[i + 1][i] += step;
  }
  for (int i = 0; i < 4; ++i) v[i] = f(p[i]);
  for (int it = 0; it < iterations; ++it) {
    std::array<int, 4> order = {0, 1, 2, 3};
    std::sort(order.begin(), order.end(), [&](int l, int r) { return v[l] < v[r]; });
    const int best = order[0], second = order[2], worst = order[3];
    if (std::fabs(v[worst] - v[best]) < 1e-7) break;
    std::array<double, 3> c = {0, 0, 0};
    for (int k = 0; k < 3; ++k)
      for (int d = 0; d < 3; ++d) c[d] += p[order[k]][d] / 3;
    auto along = [&](double t) {
      std::array<double, 3> out;
      for (int d = 0; d < 3; ++d) out[d] = c[d] + t * (p[worst][d] - c[d]);
      return out;
    };
    const auto reflected = along(-1);
    const double vr = f(reflected);
    if (vr < v[best]) {
      const auto expanded = along(-2);
      const double ve = f(expanded);
      p[worst] = ve < vr ? expanded : reflected;
      v[worst] = std::min(ve, vr);
    } else if (vr < v[second]) {
      p[worst] = reflected, v[worst] = vr;
    } else {
      const auto contracted = along(vr < v[worst] ? -0.5 : 0.5);
      const double vc = f(contracted);
      if (vc < std::min(vr, v[worst])) {
        p[worst] = contracted, v[worst] = vc;
      } else {
        for (int k = 0; k < 4; ++k) {
          if (k == best) continue;
          for (int d = 0; d < 3; ++d) p[k][d] = p[best][d] + 0.5 * (p[k][d] - p[best][d]);
          v[k] = f(p[k]);
        }
      }
    }
  }
  const int best = static_cast<int>(std::min_element(v.begin(), v.end()) - v.begin());
  x = p[best];
  return v[best];
}

nb::dict gjr_fit(In x_) {
  const int64_t n = static_cast<int64_t>(x_.shape(0));
  if (n < 50) throw std::invalid_argument("GJR-GARCH braucht mindestens 50 Beobachtungen");
  const double* x = x_.data();
  for (int64_t t = 0; t < n; ++t)
    if (!std::isfinite(x[t])) throw std::invalid_argument("GJR-GARCH: Eingabe enthaelt NaN oder Inf");
  std::vector<double> e(n), sigma2(n), z(n);
  double mean = 0, var = 0, alpha = 0, gamma = 0, beta = 0, omega = 0, next_var = 0, peak_var = 0;
  {
    nb::gil_scoped_release release;
    for (int64_t t = 0; t < n; ++t) mean += x[t];
    mean /= n;
    for (int64_t t = 0; t < n; ++t) {
      e[t] = x[t] - mean;
      var += e[t] * e[t];
    }
    var /= n;
    if (var > 1e-16) {  // Eine konstante Reihe hat keine Schwankung: alles bleibt 0
      auto objective = [&](const std::array<double, 3>& p) { return gjr_nll(e.data(), n, p[0], p[1], p[2], var); };
      const std::array<std::array<double, 3>, 4> starts = {{{0.05, 0.05, 0.85}, {0.02, 0.10, 0.85}, {0.10, 0.02, 0.80}, {0.05, 0.0, 0.70}}};
      double best = std::numeric_limits<double>::infinity();
      std::array<double, 3> best_p = starts[0];
      for (const auto& start : starts) {
        std::array<double, 3> p = start;
        const double value = nelder_mead(objective, p, 0.02, 300);
        if (value < best) best = value, best_p = p;
      }
      alpha = best_p[0], gamma = best_p[1], beta = best_p[2];
      omega = var * (1 - alpha - 0.5 * gamma - beta);
      double s2 = var;
      for (int64_t t = 0; t < n; ++t) {
        sigma2[t] = s2;
        z[t] = e[t] / std::sqrt(s2);
        peak_var = std::max(peak_var, s2);
        s2 = omega + (alpha + (e[t] < 0 ? gamma : 0.0)) * e[t] * e[t] + beta * s2;
      }
      next_var = s2;
    }
  }
  nb::dict d;
  d["mean"] = mean, d["var"] = var, d["alpha"] = alpha, d["gamma"] = gamma, d["beta"] = beta, d["omega"] = omega;
  d["next_var"] = next_var, d["peak_var"] = peak_var;
  d["sigma2"] = to_numpy(std::move(sigma2));
  d["z"] = to_numpy(std::move(z));
  return d;
}

// Korrelation zweier standardisierter Reihen plus Zirkular-Shift-Test: Die Verschiebung zerstoert den Zusammenhang,
// erhaelt aber die Autokorrelation. So gelten zwei traege Reihen nicht schon deshalb als verwandt, weil beide traege sind.
nb::tuple ic_test(In x_, In y_, int64_t n_shift, uint64_t seed) {
  const int64_t n = static_cast<int64_t>(x_.shape(0));
  if (static_cast<int64_t>(y_.shape(0)) != n || n < 3) throw std::invalid_argument("ic_test: Reihen muessen gleich lang sein");
  const double* x = x_.data();
  const double* y = y_.data();
  auto dot = [](const double* a, const double* b, int64_t len) {
    double sum = 0;
    for (int64_t i = 0; i < len; ++i) sum += a[i] * b[i];
    return sum;
  };
  const double real = dot(x, y, n) / n;
  int64_t beyond = 0;
  {
    nb::gil_scoped_release release;
#pragma omp parallel for reduction(+ : beyond) schedule(static)
    for (int64_t s = 0; s < n_shift; ++s) {
      const int64_t offset = 1 + static_cast<int64_t>(splitmix64(seed + s) % uint64_t(n - 1));
      const double shifted = (dot(x, y + offset, n - offset) + dot(x + n - offset, y, offset)) / n;
      if (std::fabs(shifted) >= std::fabs(real)) ++beyond;
    }
  }
  return nb::make_tuple(real, double(1 + beyond) / double(1 + n_shift));
}

NB_MODULE(ioncore, m) {
  m.def("ic_test", &ic_test, nb::arg("x"), nb::arg("y"), nb::arg("n_shift"), nb::arg("seed") = 1);
  m.def("gjr_fit", &gjr_fit, nb::arg("x"));
  m.def("make_windows", &make_windows, nb::arg("x"), nb::arg("window"), nb::arg("length"));
  m.def("dtw", &dtw, nb::arg("query"), nb::arg("candidates"), nb::arg("band"));
  m.def("scan", &scan, nb::arg("high"), nb::arg("low"), nb::arg("close"), nb::arg("ks"));
  m.def("triple_barrier", &triple_barrier);
  m.def("control_test", &control_test);
  m.def("rolling_mfdfa", &rolling_mfdfa, nb::arg("x"), nb::arg("window"));
  m.def("rolling_mr", &rolling_mr, nb::arg("close"), nb::arg("window"));
  m.def("shift_test", &shift_test, nb::arg("fwd"), nb::arg("events"), nb::arg("n_shift"), nb::arg("seed") = 1);
  m.def("threads", [] { return omp_get_max_threads(); });
  m.def("set_threads", [](int n) { omp_set_num_threads(n); });
}

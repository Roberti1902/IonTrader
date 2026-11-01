"""IonTrader: Pattern-Matching & Predictive Analytics."""
import os
import ssl
import sys
import warnings
from pathlib import Path

import certifi
import yfinance  # noqa: F401  setzt beim Import eigene Warnfilter, deshalb vor unserem Filter
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
warnings.filterwarnings("ignore", module="yfinance")  # interne Deprecation-Warnungen der Bibliothek


def _trust_windows_roots():
    """Virenscanner wie Avast scannen TLS mit eigener Root, die certifi nicht kennt.

    Bundle = certifi + Windows-Root-Store. Die Zertifikatspruefung bleibt aktiv.
    """
    if os.name != "nt":
        return
    server_auth = "1.3.6.1.5.5.7.3.1"
    pems = [ssl.DER_cert_to_PEM_cert(der) for der, enc, trust in ssl.enum_certificates("ROOT")
            if enc == "x509_asn" and (trust is True or server_auth in trust)]
    bundle = ROOT / "data" / "ca_bundle.pem"
    bundle.parent.mkdir(exist_ok=True)
    bundle.write_text(Path(certifi.where()).read_text(encoding="ascii", errors="ignore") + "".join(pems),
                      encoding="ascii")
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ[var] = str(bundle)


_trust_windows_roots()


def exit_now():
    """Beendet den Prozess sofort. Erst aufrufen, wenn alle Ergebnisse gespeichert sind."""
    # ponytail: PyTorch 2.15 stuerzt nach CUDA-LSTMs beim Entladen der DLLs ab (auch ohne unseren Code, 0xC0000409),
    # selbst bei os._exit. TerminateProcess ueberspringt das; nach einem PyTorch-Update wieder entfernen.
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
    os._exit(0)

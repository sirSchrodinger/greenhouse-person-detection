# -*- coding: utf-8 -*-
"""
sera.rapor — TEK BİÇİMLİ çıktı: tablo, renk, JSON, markdown, durum defteri.

NEDEN: 64 script'in her biri kendi print biçimini uydurmuştu. Aynı sayı bir dosyada
"yakalanan 103/181 (%56.9)", ötekinde "TP=103 recall=0.569" diye yazıyordu; iki koşuyu
yan yana koyup kıyaslamak elle çeviri gerektiriyordu. Burada tek biçim var.

DEVRALINAN:
  · log()/baslik()/ilerleme()   ← sera_pipeline.py:98-120  (zaman damgalı satır, ETA)
  · jyaz()/joku()/durum_yaz()   ← sera_pipeline.py:200-219 (atomik yazım + durum defteri)
  · tablo düzeni                ← sera_pipeline.py:adim_olc() ızgara tablosu ("det≥ dog≥ ...")

RENK: sadece TTY'de. Boruya/dosyaya yazarken kapanır (SERA_RENK=1 zorlar, 0 kapatır).
"kırmızı" bu projede tek anlama gelir: ÖLÇÜM GEÇMEDİ. Süsleme için kullanılmaz.
"""
import os
import sys
import json
import time
import collections

from . import ayar

# ---------------------------------------------------------------- durum
BASLANGIC = time.time()
HAT = os.path.join(ayar.GATE, "pipeline")          # sera_pipeline.py:HAT ile aynı dizin
DURUM_JSON = os.path.join(HAT, "durum.json")

_RENK_ORTAM = os.environ.get("SERA_RENK")
if _RENK_ORTAM is None:
    RENK = sys.stdout.isatty()
else:
    RENK = _RENK_ORTAM.strip().lower() in ("1", "true", "yes", "evet", "on")

_K = {"kirmizi": "\033[31m", "yesil": "\033[32m", "sari": "\033[33m",
      "mavi": "\033[36m", "kalin": "\033[1m", "sifir": "\033[0m"}


def _boya(s, ad):
    if not RENK:
        return s
    return _K[ad] + str(s) + _K["sifir"]


def kirmizi(s):
    """KIRMIZI = ölçüm geçmedi / karar verilemez. Başka amaçla kullanma."""
    return _boya(s, "kirmizi")


def yesil(s):
    return _boya(s, "yesil")


def sari(s):
    return _boya(s, "sari")


def mavi(s):
    return _boya(s, "mavi")


def kalin(s):
    return _boya(s, "kalin")


# ---------------------------------------------------------------- log
def log(m="", zaman=True):
    """sera_pipeline.py:log() — süreç başlangıcından geçen saniye + satır."""
    if m == "":
        print("", flush=True)
        return
    if zaman:
        print("[%6.1fs] %s" % (time.time() - BASLANGIC, m), flush=True)
    else:
        print(m, flush=True)


def baslik(m):
    """sera_pipeline.py:baslik()."""
    log()
    log("=" * 74, zaman=False)
    log(kalin(m), zaman=False)
    log("=" * 74, zaman=False)


def alt(m):
    log()
    log("--- %s " % m + "-" * max(0, 68 - len(m)), zaman=False)


def ilerleme(k, n, t0, ek="", adim_sayisi=40):
    """Yüzde + kalan süre. sera_pipeline.py:ilerleme() — n/40 adımda bir yazar."""
    adim = max(1, n // adim_sayisi)
    if k % adim and k != n:
        return
    gec = time.time() - t0
    kalan = (gec / max(1, k)) * (n - k)
    log("   %%%-5.1f %d/%d  %.0f sn geçti, ~%.0f sn kaldı %s"
        % (100.0 * k / max(1, n), k, n, gec, kalan, ek))


# ---------------------------------------------------------------- tablo
def tablo(satirlar, basliklar=None, hiza=None, yaz=True, girinti="  "):
    """Hizalanmış metin tablosu. satirlar: list[list] veya list[dict].

    basliklar : list[str]; dict satırlarda None ise anahtarlar kullanılır.
    hiza      : "l"/"r" karakter dizisi ya da liste; None → sayı sütunları sağa yaslı.
    Dönüş: tablo metni (yaz=True ise ayrıca basılır).
    """
    if not satirlar:
        m = girinti + "(satır yok)"
        if yaz:
            log(m, zaman=False)
        return m
    if isinstance(satirlar[0], dict):
        if basliklar is None:
            basliklar = list(satirlar[0].keys())
        veri = [[r.get(k, "") for k in basliklar] for r in satirlar]
    else:
        veri = [list(r) for r in satirlar]
    n = max(len(r) for r in veri)
    if basliklar is None:
        basliklar = [""] * n
    basliklar = list(basliklar) + [""] * (n - len(basliklar))
    veri = [list(r) + [""] * (n - len(r)) for r in veri]

    metin = [[("" if v is None else ("%.4f" % v if isinstance(v, float) else str(v)))
              for v in r] for r in veri]
    if hiza is None:
        hiza = []
        for j in range(n):
            sayi = all(_sayi_mi(r[j]) for r in veri if r[j] not in ("", None))
            hiza.append("r" if sayi else "l")
    hiza = list(hiza) + ["l"] * (n - len(hiza))

    gen = [max([len(str(basliklar[j]))] + [len(r[j]) for r in metin]) for j in range(n)]

    def _sat(hucre):
        return girinti + "  ".join(
            (h.rjust(g) if a == "r" else h.ljust(g)) for h, g, a in zip(hucre, gen, hiza))

    cikti = []
    if any(basliklar):
        cikti.append(_sat([str(b) for b in basliklar]))
        cikti.append(girinti + "  ".join("-" * g for g in gen))
    cikti += [_sat(r) for r in metin]
    s = "\n".join(cikti)
    if yaz:
        for satir in cikti:
            log(satir, zaman=False)
    return s


def _sayi_mi(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def sayac(deger_listesi, baslik_=None, yaz=True):
    """Dağılım tablosu: {'var': 314, 'yok': 512, ...} biçiminde tek satır özet."""
    c = deger_listesi if isinstance(deger_listesi, dict) else dict(
        collections.Counter(deger_listesi))
    s = " · ".join("%s %s" % (k, c[k]) for k in sorted(c, key=lambda x: (str(x))))
    if yaz:
        log(("%s: %s" % (baslik_, s)) if baslik_ else s)
    return c


# ---------------------------------------------------------------- JSON
def jyaz(yol, veri):
    """Atomik JSON yazımı — sera_pipeline.py:jyaz(). Yarım dosya bırakmaz."""
    d = os.path.dirname(os.path.abspath(yol))
    if d:
        os.makedirs(d, exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w") as f:
        json.dump(veri, f, default=float)
    os.replace(gecici, yol)
    return yol


def joku(yol, varsayilan=None):
    """sera_pipeline.py:joku() — okunamıyorsa patlamaz, varsayılanı döner."""
    try:
        with open(yol) as f:
            return json.load(f)
    except Exception:
        return varsayilan


# ---------------------------------------------------------------- durum defteri
def durum_yaz(adim, ozet_metni, ek=None):
    """gate/pipeline/durum.json — "en son ne çalıştı, ne çıktı". sera_pipeline.py:durum_yaz()."""
    d = joku(DURUM_JSON, {}) or {}
    kayit = {"ts": int(time.time()), "tarih": time.strftime("%Y-%m-%d %H:%M"),
             "ozet": ozet_metni}
    if ek:
        kayit.update(ek)
    d[adim] = kayit
    jyaz(DURUM_JSON, d)
    return d


def durum_oku():
    return joku(DURUM_JSON, {}) or {}


def yas(ts):
    """epoch → "3 sa 12 dk önce" (durum raporu için)."""
    if not ts:
        return "-"
    s = max(0, int(time.time() - float(ts)))
    if s < 90:
        return "%d sn önce" % s
    if s < 5400:
        return "%d dk önce" % (s // 60)
    if s < 172800:
        return "%d sa %d dk önce" % (s // 3600, (s % 3600) // 60)
    return "%d gün önce" % (s // 86400)


def dosya_yasi(yol):
    """(var_mi, "3 sa önce", boyut_mb)."""
    try:
        st = os.stat(yol)
        return True, yas(st.st_mtime), st.st_size / 1e6
    except Exception:
        return False, "-", 0.0


# ---------------------------------------------------------------- özet satırı
def ozet(komut, mesaj, yol=None):
    """HER komutun son satırı bu biçimde: 'ÖZET · <komut>: <mesaj>  -> <yol>'."""
    s = "ÖZET · %s: %s" % (komut.upper(), mesaj)
    if yol:
        s += "   -> %s" % yol
    log()
    log(kalin(s), zaman=False)
    return s


# ---------------------------------------------------------------- markdown
def markdown(bas, bolumler, yol=None):
    """bolumler: [(altbaslik, metin_veya_satirlar)] → markdown metni (istenirse dosyaya)."""
    p = ["# %s" % bas, "", "_%s_" % time.strftime("%Y-%m-%d %H:%M"), ""]
    for ad, icerik in bolumler:
        p.append("## %s" % ad)
        p.append("")
        if isinstance(icerik, (list, tuple)):
            icerik = "\n".join(str(x) for x in icerik)
        p.append("```\n%s\n```" % icerik if "\n" in str(icerik) else str(icerik))
        p.append("")
    m = "\n".join(p)
    if yol:
        d = os.path.dirname(os.path.abspath(yol))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(yol, "w") as f:
            f.write(m)
    return m


if __name__ == "__main__":
    baslik("sera.rapor gösterim")
    tablo([{"det": 0.52, "dog": "cam", "yakalanan": 103, "yanlis": 4},
           {"det": 0.20, "dog": 0.70, "yakalanan": 132, "yanlis": 4}])
    log()
    log("kırmızı örneği: " + kirmizi("ÖLÇÜM GEÇMEDİ"))
    log("yeşil örneği  : " + yesil("kontrol geçti"))
    d = durum_oku()
    log()
    log("durum defteri (%s):" % DURUM_JSON)
    for k, v in d.items():
        log("  %-9s %-18s %s" % (k, yas(v.get("ts")), v.get("ozet")))

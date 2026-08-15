# -*- coding: utf-8 -*-
"""sera.dedektor — YOLO11s ileri geçişinin TEK doğru uygulaması.

NEDEN BU DOSYA VAR
------------------
2 Ağustos 2026 itibarıyla aynı ileri geçiş en az 5 dosyada kopyalanmıştı ve hepsi
biraz farklıydı. Hata tam olarak bu farklardan çıkıyordu:

  kaynak dosya                                     eşik   kutu sınırlama   çoklu kutu  NMS
  -----------------------------------------------  -----  ---------------  ----------  ----
  hacim_kuru.py                (person-detect/)     0.05   var (0..ww/hh)   YOK (max)   yok
  full_scan.py                 (person-detect/)     0.05   var + round(,1)  YOK (max)   yok
  retro_build.py:skor          (person-detect/)     0.03   kutu döndürmez   YOK (max)   yok
  suphe_grid.py                (scratchpad/)        0.03   YOK              YOK (max)   yok
  coklu_kutu.py:kutular        (person-detect/)     0.03   var (0..ww/hh)   VAR         0.45
  olay_denetim2.py:Motor.kutular (person-detect/)   0.03   YOK              VAR         yok

Bu modül bunların birleşimidir; sayısal davranış korunmuştur (bkz. DOĞRULAMA notu
en altta). Ölçek/letterbox/geri-çevirme aritmetiği harfi harfine yukarıdaki
dosyalardan alındı — özellikle suphe_grid.py:skorla ve coklu_kutu.py:kutular
doğru geri-çevirme örneğidir.

ÜRETİM REFERANSI: vps/person_watch_v3.py:letterbox + person_in (DEĞİŞTİRİLMEDİ,
sadece okundu). İki bilinçli fark, ikisi de arşiv-tarafı davranışını korumak için:
  1) Model seçimi: üretim `hd=True` argümanıyla seçer; arşiv tarafı KARE BOYUTUNDAN
     çıkarır → max(h, w) >= 700 ise 960, değilse 640. Buradaki kural arşiv kuralıdır.
  2) Kutu sınırlama: üretim `min(W-1, int(x2))` ile int'e yuvarlar; arşiv tarafı
     `min(ww, x2)` ile float bırakır. Burada arşiv (float) davranışı korundu, çünkü
     hacim_kuru.json / full_scan.json / coklu_kutu.json hep bununla üretildi.

TEK SAYISAL FARK (ölçüldü, zararsız): hacim_kuru.py ve coklu_kutu.py kutu
aritmetiğini np.float32 ile yapıyordu (`cx, cy, bw2, bh2 = o[j, 0:4]`); burada
suphe_grid.py / olay_denetim2.py gibi float64'e çevrilir. A/B'de ölçülen en büyük
sapma 1202 px'lik bir koordinatta 0.000112 px (bağıl hata ~1e-10) — üstelik kırpma
zaten int()'e yuvarladığı için aşağı akışta tamamen kaybolur. Skorlar bit-birebir.

MANTIK KORUNDU — eşik/sabit DEĞİŞTİRİLMEDİ:
  · MIN_AREA 0.0018  (letterbox alanı üzerinden: (bw*bh)/size**2)
  · det taban eşiği 0.03
  · letterbox dolgusu 114, orantılı ölçek r = min(size/h, size/w)
  · sınıf 0 = person; argmax(o[j, 4:]) != 0 ise kutu atılır
  · çıkış tensörü o.shape[0] < o.shape[1] ise transpoze edilir

API (diğer modüller buna göre yazıyor — imzayı bozma):
    d = Dedektor()
    d.kutular(img_veya_yol, esik=0.03, min_alan=0.0018) -> list[dict]
        her kutu: {"skor": float, "kutu": [x1,y1,x2,y2] ORİJİNAL kare koordinatı, "hd": bool}
        skora göre AZALAN sıralı
    d.en_iyi(img_veya_yol, ...) -> dict | None
"""

import os
import threading

import numpy as np
import cv2

# ---------------------------------------------------------------- ayarlar
# sera.ayar TEK gerçek kaynaktır — SERT import, yedek literal YOK.
# ⚠ 2 Ağu: burada `try/except → _ayar=None` ve her sabitin yanında bir yedek literal
#   vardı ("paket kademeli taşınıyor" dönemi). Taşıma bitti; yedekler ayar.py'nin
#   ikinci bir kopyasıydı. ayar.py bozulursa modül SESSİZCE eski sabitle çalışmasın,
#   YÜKSEK SESLE patlasın diye kaldırıldı.
from . import ayar as _ayar


def _a(ad):
    """ayar.py'den oku; SERA_<AD> ortam değişkeni ezer. ayar'da yoksa AttributeError."""
    d = getattr(_ayar, ad)
    o = os.environ.get("SERA_" + ad)
    if o is None:
        return d
    if isinstance(d, bool):
        return o.strip().lower() in ("1", "true", "yes", "evet")
    if isinstance(d, int) and not isinstance(d, bool):
        return int(o)
    if isinstance(d, float):
        return float(o)
    return o


KOK        = _a("KOK")
YOLO640    = _a("YOLO640")
YOLO960    = _a("YOLO960")

DET_ESIK   = float(_a("DET_ESIK"))     # kutu üretme tabanı (karar eşiği DEĞİL)
MIN_ALAN   = float(_a("MIN_ALAN"))     # (bw*bh)/size**2
HD_KENAR   = int(_a("HD_KENAR"))       # max(h,w) >= bu ise 960 modeli
BOYUT_640  = int(_a("BOYUT_640"))
BOYUT_960  = int(_a("BOYUT_960"))
DOLGU      = int(_a("DOLGU"))          # letterbox dolgu rengi
PERSON_SINIF = int(_a("PERSON_SINIF"))  # COCO sınıf 0 = person
IPLIK      = int(_a("IPLIK"))

# ---------------------------------------------------------------- oturum önbelleği
# "Aynı süreçte iki kez model yükleme" — yolo11s_960.onnx 38 MB, yükleme ~2 sn.
# Anahtar (yol, iplik); değer (InferenceSession, giris_adi).
_ONBELLEK = {}
_KILIT = threading.Lock()


def _oturum(yol, iplik):
    anahtar = (os.path.realpath(yol), int(iplik))
    with _KILIT:
        if anahtar in _ONBELLEK:
            return _ONBELLEK[anahtar]
        import onnxruntime as ort
        if not os.path.isfile(yol):
            raise FileNotFoundError("ONNX modeli yok: %s" % yol)
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(iplik)
        s = ort.InferenceSession(yol, so, providers=["CPUExecutionProvider"])
        cift = (s, s.get_inputs()[0].name)
        _ONBELLEK[anahtar] = cift
        return cift


def onbellek_temizle():
    """Testte/uzun süreçte belleği bırakmak için."""
    with _KILIT:
        _ONBELLEK.clear()


# ---------------------------------------------------------------- yardımcılar
def letterbox(img, boyut, dolgu=DOLGU):
    """Orantılı ölçek + ortalanmış dolgu. vps/person_watch_v3.py:letterbox ile aynı.

    Dönüş: (tuval, r, dw, dh) — geri çevirme: x_orj = (x_lb - dw) / r
    """
    h, w = img.shape[:2]
    r = min(boyut / h, boyut / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    tuval = np.full((boyut, boyut, 3), dolgu, np.uint8)
    dw, dh = (boyut - nw) // 2, (boyut - nh) // 2
    tuval[dh:dh + nh, dw:dw + nw] = cv2.resize(img, (nw, nh))
    return tuval, r, dw, dh


def _iou_min(a, b):
    """Kesişim / küçük kutunun alanı. coklu_kutu.py:kutular içindeki basit NMS ölçütü."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    if ix <= 0 or iy <= 0:
        return 0.0
    a1 = (a[2] - a[0]) * (a[3] - a[1])
    a2 = (b[2] - b[0]) * (b[3] - b[1])
    kucuk = min(a1, a2)
    return (ix * iy) / kucuk if kucuk > 0 else 0.0


def _goruntu(img_veya_yol):
    """str yol ya da BGR ndarray kabul et. Okunamazsa None."""
    if img_veya_yol is None:
        return None
    if isinstance(img_veya_yol, np.ndarray):
        return img_veya_yol
    return cv2.imread(str(img_veya_yol))


# ---------------------------------------------------------------- dedektör
class Dedektor:
    """YOLO11s person dedektörü — 640 alt-akış / 960 HD, tek uygulama.

    Örnek:
        d = Dedektor()
        for k in d.kutular("/mnt/data/sera-arsiv/timeline/kamera1/20260718/0121.jpg"):
            print(k["skor"], k["kutu"], k["hd"])
    """

    def __init__(self, onnx640=None, onnx960=None, threads=None):
        self.onnx640 = onnx640 or YOLO640
        self.onnx960 = onnx960 or YOLO960
        self.threads = int(threads) if threads else IPLIK
        self._s6 = self._n6 = None
        self._s9 = self._n9 = None

    # -- oturumlar tembel açılır: sadece 640 kare geliyorsa 960 hiç yüklenmez
    def _al(self, hd):
        if hd:
            if self._s9 is None:
                self._s9, self._n9 = _oturum(self.onnx960, self.threads)
            return self._s9, self._n9, BOYUT_960
        if self._s6 is None:
            self._s6, self._n6 = _oturum(self.onnx640, self.threads)
        return self._s6, self._n6, BOYUT_640

    def hd_mi(self, img):
        """Kare boyutundan model seçimi: max(h, w) >= 700 → 960 modeli."""
        return bool(max(img.shape[:2]) >= HD_KENAR)

    # ------------------------------------------------------------ ileri geçiş
    def _ileri(self, img):
        """Ham ileri geçiş. Dönüş: (o, r, dw, dh, size, hd, ww, hh).

        o: (N, 4+sinif) düzeninde çıkış (gerekliyse transpoze edilmiş).
        """
        hd = self.hd_mi(img)
        sess, iname, size = self._al(hd)
        hh, ww = img.shape[:2]
        lb, r, dw, dh = letterbox(img, size)
        b = np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1), np.float32) / 255.0
        o = sess.run(None, {iname: b[None]})[0][0]
        if o.shape[0] < o.shape[1]:          # (84, 8400) → (8400, 84)
            o = o.transpose(1, 0)
        return o, r, dw, dh, size, hd, ww, hh

    # ------------------------------------------------------------ ana API
    def kutular(self, img_veya_yol, esik=DET_ESIK, min_alan=MIN_ALAN,
                nms=None, sinirla=True, en_fazla=None):
        """Karedeki TÜM person kutuları, skora göre azalan.

        Parametreler
          esik      : ham skor tabanı (varsayılan 0.03 — kutu üretme tabanı, karar eşiği değil)
          min_alan  : (bw*bh)/size**2 alt sınırı (varsayılan 0.0018)
          nms       : None → NMS YOK (hacim_kuru / full_scan / olay_denetim2 davranışı).
                      Sayı verilirse coklu_kutu.py'deki basit NMS uygulanır (orada 0.45).
          sinirla   : kutuyu [0, ww] x [0, hh] içine kırp (hacim_kuru/full_scan/coklu_kutu
                      böyle yapıyordu; suphe_grid/olay_denetim2 yapmıyordu — skoru etkilemez)
          en_fazla  : en yüksek skorlu ilk N kutu (coklu_kutu.py'de TOPK=6)

        Dönüş: list[dict] — {"skor": float, "kutu": [x1,y1,x2,y2], "hd": bool}
        Kare okunamazsa boş liste.
        """
        img = _goruntu(img_veya_yol)
        if img is None:
            return []
        o, r, dw, dh, size, hd, ww, hh = self._ileri(img)

        pr = o[:, 4]                                  # sınıf 0 = person sütunu
        cikti = []
        for j in np.where(pr >= esik)[0]:
            if int(np.argmax(o[j, 4:])) != PERSON_SINIF:
                continue                              # araç/eşya person'a benzemesin
            cx, cy, bw, bh = [float(v) for v in o[j, 0:4]]
            if (bw * bh) / (size ** 2) < min_alan:
                continue
            x1 = (cx - bw / 2 - dw) / r
            y1 = (cy - bh / 2 - dh) / r
            x2 = (cx + bw / 2 - dw) / r
            y2 = (cy + bh / 2 - dh) / r
            if sinirla:
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(float(ww), x2), min(float(hh), y2)
            cikti.append({"skor": float(pr[j]), "kutu": [x1, y1, x2, y2], "hd": hd})

        # kararlı sıralama: eşit skorda ilk bulunan önde kalır (eski `> best` ile aynı seçim)
        cikti.sort(key=lambda k: -k["skor"])

        if nms is not None:
            tut = []
            for k in cikti:
                if all(_iou_min(k["kutu"], t["kutu"]) <= nms for t in tut):
                    tut.append(k)
                if en_fazla and len(tut) >= en_fazla:
                    break
            return tut
        if en_fazla:
            return cikti[:en_fazla]
        return cikti

    def en_iyi(self, img_veya_yol, esik=DET_ESIK, min_alan=MIN_ALAN, sinirla=True):
        """En yüksek skorlu person kutusu ya da None.

        Kolaylık sarmalayıcısı — asıl iş kutular()'da. Tek-kutu darboğazı için
        bkz. coklu_kutu.py: karede iki nesne varsa (varil 0.31 · insan 0.12) bu
        fonksiyon VARİLİ döndürür. Doğrulayıcıya besliyorsan kutular() kullan.
        """
        k = self.kutular(img_veya_yol, esik=esik, min_alan=min_alan, sinirla=sinirla)
        return k[0] if k else None

    def skor(self, img_veya_yol, esik=DET_ESIK, min_alan=MIN_ALAN):
        """Sadece en yüksek det skoru (kutu yok). retro_build.py:skor ile aynı; yoksa 0.0."""
        k = self.en_iyi(img_veya_yol, esik=esik, min_alan=min_alan)
        return k["skor"] if k else 0.0

    def ham_en_iyi(self, img_veya_yol):
        """Eşik ve alan gözetmeksizin, person'ın en üst sınıf olduğu en iyi skor.

        vps/person_watch_v3.py:person_in içindeki `raw_best` ile aynı. HD-tetik ve
        'hd-red' kapısının kullandığı büyüklük budur — "model bu karede kişiyi ne
        kadar gördü". Aynı çıkarımdan bedava; ayrı düşük-eşik geçişi YOK.
        """
        img = _goruntu(img_veya_yol)
        if img is None:
            return 0.0
        o, r, dw, dh, size, hd, ww, hh = self._ileri(img)
        pr = o[:, 4]
        if pr.size == 0:
            return 0.0
        p_mi = np.argmax(o[:, 4:], axis=1) == PERSON_SINIF
        return float(np.where(p_mi, pr, 0.0).max())

    def tara(self, img_veya_yol, esik=DET_ESIK, min_alan=MIN_ALAN, **kw):
        """Tek çıkarımda hem kutular hem ham skor — iki kez model çalıştırmamak için.

        Dönüş: {"kutular": [...], "ham": float, "hd": bool, "boyut": (h, w)}
        """
        img = _goruntu(img_veya_yol)
        if img is None:
            return {"kutular": [], "ham": 0.0, "hd": False, "boyut": None}
        o, r, dw, dh, size, hd, ww, hh = self._ileri(img)
        pr = o[:, 4]
        p_mi = np.argmax(o[:, 4:], axis=1) == PERSON_SINIF
        ham = float(np.where(p_mi, pr, 0.0).max()) if pr.size else 0.0

        sinirla = kw.get("sinirla", True)
        cikti = []
        for j in np.where(pr >= esik)[0]:
            if not p_mi[j]:
                continue
            cx, cy, bw, bh = [float(v) for v in o[j, 0:4]]
            if (bw * bh) / (size ** 2) < min_alan:
                continue
            x1 = (cx - bw / 2 - dw) / r
            y1 = (cy - bh / 2 - dh) / r
            x2 = (cx + bw / 2 - dw) / r
            y2 = (cy + bh / 2 - dh) / r
            if sinirla:
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(float(ww), x2), min(float(hh), y2)
            cikti.append({"skor": float(pr[j]), "kutu": [x1, y1, x2, y2], "hd": hd})
        cikti.sort(key=lambda k: -k["skor"])

        nms, en_fazla = kw.get("nms"), kw.get("en_fazla")
        if nms is not None:
            tut = []
            for k in cikti:
                if all(_iou_min(k["kutu"], t["kutu"]) <= nms for t in tut):
                    tut.append(k)
                if en_fazla and len(tut) >= en_fazla:
                    break
            cikti = tut
        elif en_fazla:
            cikti = cikti[:en_fazla]
        return {"kutular": cikti, "ham": ham, "hd": hd, "boyut": (hh, ww)}


# ---------------------------------------------------------------- süreç tekili
_TEKIL = None


def varsayilan():
    """Süreç başına tek Dedektor. Kısa scriptlerde `varsayilan().kutular(p)` yeter."""
    global _TEKIL
    if _TEKIL is None:
        _TEKIL = Dedektor()
    return _TEKIL


# ---------------------------------------------------------------- DOĞRULAMA notu
# `python -m sera.dedektor` çalıştırıldığında gate/hacim_kuru.json'dan rastgele 40
# kayıt yeniden skorlanır ve ESKİ det skorlarıyla karşılaştırılır (tolerans 0.01).
# hacim_kuru.py eşiği 0.05 idi; kayıtlı det'lerin hepsi >= 0.05 olduğundan buradaki
# 0.03 tabanı EN YÜKSEK skoru değiştirmez — kıyas geçerlidir.
if __name__ == "__main__":                # pragma: no cover
    import json
    import random
    import time
    import argparse

    ap = argparse.ArgumentParser(description="dedektor.py mantık-koruma doğrulaması")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--tohum", type=int, default=20260802)
    ap.add_argument("--tolerans", type=float, default=0.01)
    ap.add_argument("--kaynak", default="/mnt/data/sera-arsiv/gate/hacim_kuru.json")
    a = ap.parse_args()

    kayit = json.load(open(a.kaynak))["kayit"]
    random.seed(a.tohum)
    ornek = random.sample(kayit, min(a.n, len(kayit)))
    print("DOGRULAMA — %s icinden %d kayit (tohum %d, tolerans %.3f)"
          % (os.path.basename(a.kaynak), len(ornek), a.tohum, a.tolerans), flush=True)

    d = Dedektor()
    sapan, kutu_sapan, yok, t0 = [], [], 0, time.time()
    for i, r in enumerate(ornek):
        k = d.en_iyi(r["p"])
        yeni = k["skor"] if k else 0.0
        fark = abs(yeni - float(r["det"]))
        if k is None:
            yok += 1
        if fark > a.tolerans:
            sapan.append((r["p"], r["det"], yeni, fark))
        if k is not None and r.get("box"):
            kf = max(abs(float(x) - float(y)) for x, y in zip(k["kutu"], r["box"]))
            if kf > 1.0:                   # eski kayit round(,1) — 1 px tolerans
                kutu_sapan.append((r["p"], r["box"], [round(v, 1) for v in k["kutu"]], kf))
        if (i + 1) % 10 == 0:
            print("  %d/%d  (%.0f sn)" % (i + 1, len(ornek), time.time() - t0), flush=True)

    print("\nkutu bulunamayan     : %d/%d" % (yok, len(ornek)))
    print("det farki > %.3f     : %d/%d" % (a.tolerans, len(sapan), len(ornek)))
    for p, e, y, f in sapan[:10]:
        print("   SAPMA %.4f -> %.4f (%.4f)  %s" % (e, y, f, p))
    print("kutu farki > 1.0 px  : %d/%d" % (len(kutu_sapan), len(ornek)))
    for p, e, y, f in kutu_sapan[:5]:
        print("   KUTU %s -> %s (%.1f px)  %s" % (e, y, f, p))
    print("\nSONUC:", "GECTI — mantik korundu" if not sapan else "KALDI — mantik bozulmus")

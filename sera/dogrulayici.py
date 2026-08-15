# -*- coding: utf-8 -*-
"""sera.dogrulayici — DINOv2 gömü + lojistik kafa. Doğrulayıcının TEK doğru uygulaması.

NEDEN BU DOSYA VAR
------------------
"Bu kutu gerçekten insan mı" sorusunu cevaplayan aynı ileri geçiş + aynı lojistik kafa
en az 6 dosyada kopyalanmıştı ve gömü önbelleği her birinde biraz farklı yönetiliyordu:

  kaynak dosya                          kırpma        önbellek                 kafa
  ------------------------------------  ------------  -----------------------  --------------------
  vps/verifier.py            (ÜRETİM)   head["kirp"]  yok (tek kare)           /opt/sera/models/...
  train_verifier3.py:gomuler            96x192 PAD.25 ARTIMLI (946 + 763)      egitim çıktısı
  train_verifier2.py                    96x192 PAD.25 tam yeniden hesap        egitim çıktısı
  oof_sweep.py                          96x192 PAD.25 oof_gomu.npz             yok (OOF)
  etiket_denetim.py                     96x192 PAD.25 gomu3.npz (3 gövde)      yok (OOF)
  esik_sweep.py / full_scan.py          96x192 PAD.25 yok                      verifier_head.json

Devralınan mantık:
  · kirp/hazirla            ← sera.gorsel'e DEVREDİLDİ (kopya yok). gorsel gövdesi
                              train_verifier3.py:kirp/:hazirla ile birebir aynıdır ve üretimdeki
                              vps/verifier.py:_kirp ile aynı aritmetiği kullanır. ÜRETİM kırpma
                              parametrelerini head["kirp"]'ten okur; biz de kafadaki kirp ile
                              sera.ayar'daki değerleri karşılaştırır, sapma varsa UYARIRIZ.
  · ARTIMLI gömü önbelleği  ← train_verifier3.py:gomuler  (npz'den fid eşleşenleri devral,
                              sadece yenileri hesapla; iki önbellek okunur, İLKİ kazanır)
  · lojistik skor           ← vps/verifier.py:skor  (z=(f-mean)/scale, t=z·coef+b, sigmoid)
  · eşik politikası         ← weights/verifier_head.json: esik_guvenli 0.50 · esik_agresif 0.85

MANTIK KORUNDU — hiçbir eşik/sabit değiştirilmedi:
  W=96 · H=192 · PAD=0.25 · giris=224 · ImageNet mean/std · gömü boyutu 768
  canlı çalışma noktası 0.50 (weights/verifier_head.json → esik_guvenli)

⚠ ÜRETİMDE BİLİNEN AÇIK (bu modül düzeltmez, sadece belgeler):
  vps/person_watch_v3.py:  `if do_fire and _verifier is not None and det_box:`
  Şüpheli kapıları (hd-red / tekrar-statik / cok-olcek) ateşi kestiğinde doğrulayıcı HİÇ
  çalışmıyor. Ölçüldü: doğrulayıcı >=0.50 ile ateşlenseydi 16 GERÇEK insan kurtulur,
  0 yanlış geçerdi. Düzeltme yeri sera/olay.py + üretim tarafı; burası değil.
  (Sayının TEK kaynağı sera.olay.kapi_bulgusu(); elle güncelleme, `durum` tazesini basar.)

API (diğer modüller buna göre yazıyor — imzayı bozma):
    d = Dogrulayici()                        # onnx=None, kafa_json=None, threads=None
    d.gomu(img, kutu)          -> np.ndarray(768,) | None     (kırpma tutmazsa None)
    d.gomuler(kayitlar, onbellek_yolu=None) -> (kayitlar, F)  ARTIMLI; F: (n,768) float32
    d.skor(img, kutu)          -> float 0..1 | None           (üretim gibi fail-open)
    d.skorlar(F)               -> np.ndarray(n,) float32
    d.gecer(s)                 -> bool                        (s >= esik)
    d.esik                     -> 0.50   (canlı çalışma noktası)
    d.esik_agresif             -> 0.85
    d.bilgi()                  -> dict
"""

import os
import json
import time
import threading

import numpy as np
import cv2

# ---------------------------------------------------------------- ayarlar
# sera.ayar TEK gerçek kaynaktır — SERT import, yedek literal YOK.
# ⚠ 2 Ağu: burada `try/except → _ayar=None` ve her sabitin yanında bir yedek literal
#   vardı (96/192/0.25/224/0.50/0.85 ayar.py'nin ikinci kopyasıydı). KIRPMA sabitleri
#   için bu özellikle tehlikeliydi: sessizce farklı bir kırpmaya düşmek tüm skorları
#   anlamsız yapar ama hiçbir hata vermez. Taşıma bitti, yedekler kaldırıldı.
from . import ayar as _ayar


def _a(adlar):
    """ayar.py'den oku (ilk eşleşen ad kazanır); SERA_<AD> ortam değişkeni ezer.

    `adlar` demet olabilir: ilk sıradaki ayar.py'nin KANONİK adı, sonrakiler bu modülün
    eski/yerel adları. Böylece ayar.py adı değiştirse de bağ kopmaz.
    Hiçbiri ayar.py'de yoksa AttributeError — sessiz varsayılan YOK.
    """
    adlar = (adlar,) if isinstance(adlar, str) else tuple(adlar)
    for ad in adlar:
        if hasattr(_ayar, ad):
            d = getattr(_ayar, ad)
            break
    else:
        raise AttributeError("sera.ayar'da bu adlardan hicbiri yok: %s" % (adlar,))
    o = None
    for ad in adlar:
        o = os.environ.get("SERA_" + ad)
        if o is not None:
            break
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
ARSIV      = _a("ARSIV")
GOVDE_ONNX = _a(("DINOV2", "GOVDE_ONNX"))
KAFA_JSON  = _a(("KAFA", "KAFA_JSON"))

# ARTIMLI önbellek: sırayla okunur, İLKİ kazanır (train_verifier3.py:gomuler ile aynı sıra).
# İlk yol aynı zamanda YAZMA yoludur.
GOMU_946   = _a("GOMU_946")
GOMU_763   = _a("GOMU_763")

# ⚠ KIRPMA — kafa hangi geometriyle eğitildiyse çıkarımda AYNISI olmalı (_kirp_kontrol
#   uyarır). Değer tek yerde: ayar.KIRP_W / KIRP_H / PAD / GIRIS.
KIRP_W     = int(_a("KIRP_W"))
KIRP_H     = int(_a("KIRP_H"))
KIRP_PAD   = float(_a(("PAD", "KIRP_PAD")))
KIRP_GIRIS = int(_a(("GIRIS", "KIRP_GIRIS")))
GOMU_BOYUT = int(_a("GOMU_BOYUT"))

ESIK_GUVENLI = float(_a(("DOG_ESIK", "ESIK_GUVENLI")))          # CANLI çalışma noktası
ESIK_AGRESIF = float(_a(("DOG_ESIK_AGRESIF", "ESIK_AGRESIF")))

# train_verifier3.py:gomuler ile aynı: dedektörü aç bırakmamak için yarım çekirdek.
# (Bilinçli olarak ayar.IPLIK'ten AYRI: o tam çekirdek, dedektör tarama içindir.)
DOG_IPLIK  = int(_a("DOG_IPLIK"))


# ---------------------------------------------------------------- kırpma / hazırlama
# TEK GERÇEK KAYNAK sera.gorsel. Kopyalamıyoruz: bir piksellik sapma tüm skorları kaydırır.
# gorsel.kirp / gorsel.hazirla gövdeleri train_verifier3.py:kirp/:hazirla ile birebir aynıdır.
from .gorsel import kirp, hazirla  # noqa: E402


# ---------------------------------------------------------------- oturum önbelleği
# verifier_dinov2.onnx 346 MB — aynı süreçte iki kez yüklemek dakikalar yer.
_ONBELLEK = {}
_KILIT = threading.Lock()


def _oturum(yol, iplik):
    anahtar = (os.path.realpath(yol), int(iplik))
    with _KILIT:
        if anahtar in _ONBELLEK:
            return _ONBELLEK[anahtar]
        import onnxruntime as ort
        if not os.path.isfile(yol):
            raise FileNotFoundError("gövde ONNX yok: %s" % yol)
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(iplik)
        s = ort.InferenceSession(yol, so, providers=["CPUExecutionProvider"])
        cift = (s, s.get_inputs()[0].name)
        _ONBELLEK[anahtar] = cift
        return cift


def onbellek_temizle():
    """Testte/uzun süreçte 346 MB'ı bırakmak için."""
    with _KILIT:
        _ONBELLEK.clear()


# ---------------------------------------------------------------- kafa
def kafa_yukle(yol=None):
    """verifier_head.json → {mean, scale, coef, b, esik_*, kirp, egitim}. np dizileri hazır."""
    yol = yol or KAFA_JSON
    h = json.load(open(yol))
    return {
        "yol": yol,
        "mean": np.array(h["mean"], np.float32),
        "scale": np.array(h["scale"], np.float32),
        "coef": np.array(h["coef"], np.float32),
        "b": float(h["intercept"]),
        "esik_guvenli": float(h.get("esik_guvenli", ESIK_GUVENLI)),
        "esik_agresif": float(h.get("esik_agresif", ESIK_AGRESIF)),
        "esik_cam": h.get("esik_cam") or {},
        "kirp": h.get("kirp") or {"W": KIRP_W, "H": KIRP_H, "PAD": KIRP_PAD, "giris": KIRP_GIRIS},
        "egitim": h.get("egitim", {}),
    }


class Dogrulayici:
    """DINOv2 gömü + lojistik kafa. Kafa dosyası opsiyonel: sadece gömü için gerekmez."""

    def __init__(self, onnx=None, kafa_json=None, threads=None):
        self.onnx = onnx or GOVDE_ONNX
        self.kafa_json = kafa_json or KAFA_JSON
        self.threads = int(threads or DOG_IPLIK)
        self._kafa = None
        self._kafa_denendi = False
        self._kirp_uyarildi = False

    # -------------------------------------------------- kafa erişimi
    @property
    def kafa(self):
        """Kafa dosyası YOKSA None döner (gömü çıkarımı kafasız da çalışır)."""
        if not self._kafa_denendi:
            self._kafa_denendi = True
            try:
                self._kafa = kafa_yukle(self.kafa_json)
                self._kirp_kontrol()
            except Exception as e:
                print("dogrulayici kafasi yuklenemedi (gomu calisir, skor calismaz): %s"
                      % str(e)[:120], flush=True)
                self._kafa = None
        return self._kafa

    def _kirp_kontrol(self):
        """Kafa hangi kırpmayla eğitildiyse çıkarımda AYNISI olmalı; sapma varsa skorlar anlamsız."""
        if self._kirp_uyarildi or not self._kafa:
            return
        k = self._kafa["kirp"]
        simdi = {"W": KIRP_W, "H": KIRP_H, "PAD": KIRP_PAD, "giris": KIRP_GIRIS}
        fark = {a: (k.get(a), simdi[a]) for a in simdi if k.get(a) is not None and k.get(a) != simdi[a]}
        if fark:
            self._kirp_uyarildi = True
            print("⚠ KIRPMA SAPMASI — kafa %s ile egitilmis, sera.gorsel bunu kullaniyor: %s"
                  % (self.kafa_json, fark), flush=True)

    @property
    def esik(self):
        """CANLI çalışma noktası (0.50). Kafa yoksa ayar/yedek değeri."""
        k = self.kafa
        return k["esik_guvenli"] if k else ESIK_GUVENLI

    @property
    def esik_agresif(self):
        k = self.kafa
        return k["esik_agresif"] if k else ESIK_AGRESIF

    def gecer(self, s):
        """Canlı politikanın tek satırı: skor >= 0.50 ise 'insan'. None → False."""
        return s is not None and float(s) >= self.esik

    # -------------------------------------------------- gömü
    def gomu(self, img, kutu):
        """Tek kare + kutu → 768 boyutlu gömü. Kırpma tutmazsa None (train_verifier3 gibi atlanır)."""
        c = kirp(img, kutu)
        if c is None:
            return None
        sess, giris = _oturum(self.onnx, self.threads)
        x = np.ascontiguousarray(hazirla(c)[None], np.float32)
        return sess.run(None, {giris: x})[0].reshape(-1)

    def gomuler(self, kayitlar, onbellek_yolu=None, ilerleme=40):
        """ARTIMLI gömü — train_verifier3.py:gomuler'den devralındı, davranış birebir.

        kayitlar : [{"fid":..., "p": <yerel yol>, "box": [x1,y1,x2,y2], ...}]
        onbellek_yolu : None → [GOMU_946, GOMU_763] (sırayla okunur, İLKİ kazanır)
                        str  → tek dosya
                        list → verilen sıra; İLK yol aynı zamanda YAZMA yoludur
        Dönüş: (tutulan_kayitlar, F)  — görüntüsü açılmayan/kırpması tutmayan kayıt DÜŞER,
        bu yüzden kayıt listesi de geri döner (F ile hizalı kalsın diye).
        """
        if onbellek_yolu is None:
            yollar = [GOMU_946, GOMU_763]
        elif isinstance(onbellek_yolu, (list, tuple)):
            yollar = list(onbellek_yolu)
        else:
            yollar = [onbellek_yolu]

        onbellek = {}
        for yol in yollar:                       # setdefault: İLK dosya kazanır
            if yol and os.path.exists(yol):
                z = np.load(yol, allow_pickle=True)
                for f, v in zip(list(z["fid"]), z["F"]):
                    onbellek.setdefault(f, v)

        eksik = [k for k in kayitlar if k["fid"] not in onbellek]
        print("gomu onbellekte %d · hesaplanacak %d" % (len(kayitlar) - len(eksik), len(eksik)),
              flush=True)
        if eksik:
            sess, giris = _oturum(self.onnx, self.threads)
            t0 = time.time()
            for i, k in enumerate(eksik):
                img = cv2.imread(k["p"])
                c = kirp(img, k["box"]) if img is not None else None
                if c is None:
                    continue
                x = np.ascontiguousarray(hazirla(c)[None], np.float32)
                onbellek[k["fid"]] = sess.run(None, {giris: x})[0].reshape(-1)
                if ilerleme and (i + 1) % ilerleme == 0:
                    print("  gomu %d/%d  (%.0f sn)" % (i + 1, len(eksik), time.time() - t0),
                          flush=True)

        tut = [k for k in kayitlar if k["fid"] in onbellek]
        F = np.stack([onbellek[k["fid"]] for k in tut]).astype(np.float32)
        if yollar and yollar[0]:
            # ⚠ 2 Ağu DENETİM: train_verifier3.py burada npz'i DÜZ ÜZERİNE yazıyordu.
            #   Orada zararsızdı (çağıran hep TAM kayıt kümesini veriyordu), ama bu artık
            #   genel bir API: `gomuler(alt_kume)` çağıran biri 862 vektörlük önbelleği
            #   sessizce alt kümeye BUDAR ve saatlerce süren gömü işi çöpe gider.
            #   Yazım artık BİRLEŞTİRME: yeni hesaplananlar kazanır, dosyadaki ötekiler kalır.
            #   Mevcut çağıranlar için sonuç sayısal olarak AYNI (kümeleri zaten tam).
            yaz_d = {}
            if os.path.exists(yollar[0]):
                z0 = np.load(yollar[0], allow_pickle=True)
                yaz_d = {f: v for f, v in zip(list(z0["fid"]), z0["F"])}
            for k in tut:
                yaz_d[k["fid"]] = onbellek[k["fid"]]
            os.makedirs(os.path.dirname(yollar[0]), exist_ok=True)
            ks = list(yaz_d.keys())
            np.savez_compressed(yollar[0],
                                F=np.array([yaz_d[k] for k in ks], np.float32),
                                fid=np.array(ks, object))
        return tut, F

    # -------------------------------------------------- skor
    def skorlar(self, F):
        """Gömü matrisi (n,768) → olasılık (n,). vps/verifier.py:skor'un vektör hâli."""
        k = self.kafa
        if k is None:
            raise RuntimeError("kafa dosyasi yok: %s" % self.kafa_json)
        F = np.asarray(F, np.float32)
        if F.ndim == 1:
            F = F[None]
        z = (F - k["mean"]) / k["scale"]
        t = z.dot(k["coef"]) + k["b"]
        return (1.0 / (1.0 + np.exp(-t))).astype(np.float32)

    def skor(self, img, kutu):
        """Tek kare + kutu → 0..1 olasılık. ÜRETİMDEKİ GİBİ FAIL-OPEN: hata/kırpma yoksa None."""
        try:
            f = self.gomu(img, kutu)
            if f is None:
                return None
            return float(self.skorlar(f)[0])
        except Exception as e:
            print("dogrulayici HATA (fail-open):", str(e)[:100], flush=True)
            return None

    # -------------------------------------------------- bilgi
    def bilgi(self):
        k = self.kafa
        return {"onnx": self.onnx, "onnx_var": os.path.isfile(self.onnx),
                "kafa": self.kafa_json, "kafa_var": k is not None,
                "iplik": self.threads, "esik": self.esik, "esik_agresif": self.esik_agresif,
                "gomu_boyut": GOMU_BOYUT,
                "kirp": k["kirp"] if k else {"W": KIRP_W, "H": KIRP_H,
                                             "PAD": KIRP_PAD, "giris": KIRP_GIRIS},
                "egitim": k["egitim"] if k else {}}


# tek örnek — kısa kullanım için (her çağrıda 346 MB yeniden yüklenmesin)
_VARSAYILAN = None


def varsayilan():
    global _VARSAYILAN
    if _VARSAYILAN is None:
        _VARSAYILAN = Dogrulayici()
    return _VARSAYILAN


def skor(img, kutu):
    """Kısa yol: varsayilan().skor(img, kutu)."""
    return varsayilan().skor(img, kutu)


if __name__ == "__main__":
    import sys
    d = Dogrulayici()
    print(json.dumps(d.bilgi(), ensure_ascii=False, indent=1, default=float))
    if len(sys.argv) > 1:
        im = cv2.imread(sys.argv[1])
        bx = [float(v) for v in sys.argv[2].split(",")] if len(sys.argv) > 2 else \
             [0, 0, im.shape[1], im.shape[0]]
        t0 = time.time()
        print("skor: %s  (%.2f sn)" % (d.skor(im, bx), time.time() - t0))

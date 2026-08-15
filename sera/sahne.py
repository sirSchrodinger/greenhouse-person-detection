# -*- coding: utf-8 -*-
"""
sera.sahne — ETİKETSİZ KAÇIRMA BULUCU: "sandalyeler oraya ne ara kondu?" (2 Ağu 2026).

Devralınan dosyalar: sahne_degisim.py (kalıcı değişim tespiti) + degisim_anlari.py
(anı daraltma + olay kaydıyla kıyas). Mantık korundu; eşik/parametre değişmedi.

ALPEREN'İN FİKRİ: sahnede bir nesne belirdiyse ya da kaybolduysa BİRİSİ ONU TAŞIMIŞTIR.
O anda insan tespiti yoksa bu KANITLANMIŞ bir kaçırmadır — hem de etiket gerektirmeden.

NEDEN DEĞERLİ: elimizdeki bütün kaçırma ölçüleri insan etiketine bağlıydı. Bu yöntem
etiketsiz çalışır ve "neyi bilmiyoruz"u "şu saatte biri vardı ve göremedik"e çevirir.
İnsan etiketi gerektirmiyor, FİZİK gerektiriyor.

YÖNTEM
  1. Her kamera için GÜNLÜK sabit-saat kareleri (öğle/ikindi — ışık en kararlı).
  2. Ardışık günleri karşılaştır; KALICI değişen bölgeleri bul. "Kalıcı" şart: geçen
     insan/gölge/yaprak değil, günün BİRDEN ÇOK saatinde duran fark.
  3. Değişimin gününü bulunca, o günün 5 dakikalık kareleriyle değişimin ANINI daralt.
  4. Olay kaydına bak: o pencerede insan tespiti var mı? Yoksa → kaçırma.

YANLIŞ POZİTİF KAYNAKLARI (bilerek eleniyor)
  · gölge/ışık        → aynı saat + ardışık gün + kalıcılık şartı
  · bitki/rüzgâr      → küçük ve dağınık; alan eşiği + morfoloji
  · kamera oynaması   → kare geneli kayarsa TÜM bölgeler değişir; global kayma testi (hizala)


╔══════════════════════════════════════════════════════════════════════════════╗
║ ÜÇ TUZAK — ÜÇÜ DE YAŞANDI, ÜÇÜNÜN DE ÇÖZÜMÜ AŞAĞIDAKİ KODDA                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
 (a) REFERANS GECE KARESİ OLURSA AN HEP GÜN DOĞUMUNA DÜŞER
     İlk tasarımda referans olarak önceki günün SON (gece) karesi alınmıştı. O zaman gün
     içindeki ilk büyük sıçrama her seferinde GÜN DOĞUMU oluyordu; ilk koşuda "kaçırma"
     diye çıkan 3 bulgunun üçü de 03:14 / 05:03 / 05:14 idi — ışık, insan değil.
     ÇÖZÜM: her kare ÖNCEKİ GÜNÜN AYNI SAATİNDEKİ karesiyle kıyaslanır.

 (b) "GÜN İÇİNDE SIÇRAMA" ŞARTI GECE OLAN DEĞİŞİMİ ATLAR
     Referans "bir önceki gün" olunca, değişim g0 içinde olduysa g1'in İLK karesinde bile
     fark yüksek çıkıyor ve an daraltılamıyor — ARABA BU YÜZDEN KAÇTI.
     ÇÖZÜM: SABİT referans günü = g0'dan bir önceki gün. Seri g0+g1 boyunca kurulur;
     ilk kalıcı yükseliş değişimin gerçek anıdır. Işık kontrolü korunur, çünkü her kare
     referans günün AYNI SAATİNDEKİ karesiyle kıyaslanır.

 (c) HAM PİKSEL FARKI IŞIĞA DUYARLI
     Şafakta birkaç dakikalık kayma bile devasa fark üretiyordu (iki koşuda da oldu).
     ÇÖZÜM: bölge SIFIR-ORTALAMA / BİRİM-SAPMA normalize edilir → parlaklık ve kontrast
     farkı silinir, geriye YAPI kalır. Nesne girip çıkması yapıyı değiştirir, ışık değiştirmez.
     (Ayrıca std < 3.0 olan düz/karanlık bölge güvenilmez sayılır ve elenir.)

Kullanım:
    from sera import sahne
    bul = sahne.kalici_degisimler()                  # tüm kameralar
    an  = [sahne.an_daralt(b) for b in bul]
    r   = sahne.olayla_kiyasla([x for x in an if x])
"""
import os
import json
import datetime as _dt
import collections

import numpy as np
import cv2

from . import ayar
from . import arsiv

# ============================================================================ sabitler
# kaynak: sahne_degisim.py:33-36  (degisim_anlari.py:KUCUK ile aynı 480)
KUCUK = int(os.environ.get("SERA_SAHNE_KUCUK", "480"))     # analiz genişliği
SAATLER = (10, 12, 14, 16)      # günlük referans saatleri (ışık kararlı)
MIN_ALAN = 0.0015               # kare alanına oran — bundan küçük değişim gürültü
KALICI_GUN = 1                  # değişim ertesi gün de duruyor mu
EN_YAKIN_DK = 45                # istenen saate bu kadar yakın kare kabul edilir
FARK_ESIK = 38                  # absdiff eşiği (sahne_degisim.py:fark_bolgeleri)
ORTUS_ESIK = 0.4                # aynı bölge sayılma örtüşmesi
KARE_GENELI = 0.7               # kare geneli değişim = ışık/kamera, elenir

# kaynak: degisim_anlari.py:27 — olay bu kadar yakınsa "açıklanmış" sayılır
YAKIN_DK = 45
GUNDUZ_BAS_DK = 7 * 60          # anı sadece kararlı ışıkta ara (07:00-19:00)
GUNDUZ_BIT_DK = 19 * 60
MIN_SERI = 20                   # bu kadar kare yoksa an daraltılamaz
MIN_REF_KARE = 20               # referans günde bu kadar kare yoksa bulgu atlanır
YUKSELIS_MIN = 0.25             # net kalıcı yükseliş eşiği (bitiş - başlangıç)
YUKSELIS_ORAN = 0.6             # eşik = d0 + (dz-d0) * bu
KALICI_KARE = 4                 # 4 ardışık kare (~20 dk) kalıcı olmalı
IMZA_MIN_STD = 3.0              # bu sapmanın altındaki bölge yapı taşımıyor

SAHNE_JSON = os.path.join(ayar.GATE, "sahne_degisim.json")
ANLAR_JSON = os.path.join(ayar.GATE, "degisim_anlari.json")


# ==========================================================================
#  KARE OKUMA
# ==========================================================================
def kareler(cam, arsiv_=None):
    """{gun: {HHMM: yol}} — BİREBİR sahne_degisim.py:kareler."""
    AR = arsiv_ or ayar.ARSIV
    d = collections.defaultdict(dict)
    import glob
    import re
    for p in sorted(glob.glob(os.path.join(AR, "timeline", "kamera%d" % int(cam),
                                           "*", "*.jpg"))):
        m = re.search(r"/(\d{8})/(\d{4})\.jpg$", p)
        if m:
            d[m.group(1)][m.group(2)] = p
    return d


def oku(p):
    """Kareyi KUCUK genişliğine küçült, gri döndür. BİREBİR sahne_degisim.py:oku."""
    im = cv2.imread(p)
    if im is None:
        return None
    h = int(im.shape[0] * KUCUK / im.shape[1])
    im = cv2.resize(im, (KUCUK, h))
    return cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)


def en_yakin(gun_d, saat):
    """O günün verilen saatine en yakın karesi (EN_YAKIN_DK içindeyse).
    BİREBİR sahne_degisim.py:en_yakin."""
    hedef = saat * 60
    en, ep = 10 ** 9, None
    for hhmm, p in gun_d.items():
        t = int(hhmm[:2]) * 60 + int(hhmm[2:])
        if abs(t - hedef) < en:
            en, ep = abs(t - hedef), p
    return ep if en <= EN_YAKIN_DK else None


# ==========================================================================
#  KALICI DEĞİŞİM  (sahne_degisim.py)
# ==========================================================================
def hizala(a, b):
    """Kamera hafif oynadıysa global kaymayı telafi et; yoksa HER YER 'değişti' görünür.

    BİREBİR sahne_degisim.py:hizala. Çok büyük kayma (>40 px) = kamera oynamış → gün atlanır.
    -> (hizalanmis_b | None, kayma)
    """
    try:
        sh = cv2.phaseCorrelate(np.float32(a), np.float32(b))[0]
        if abs(sh[0]) < 0.5 and abs(sh[1]) < 0.5:
            return b, (0.0, 0.0)
        if abs(sh[0]) > 40 or abs(sh[1]) > 40:
            return None, sh
        M = np.float32([[1, 0, -sh[0]], [0, 1, -sh[1]]])
        return cv2.warpAffine(b, M, (b.shape[1], b.shape[0])), sh
    except Exception:
        return b, (0.0, 0.0)


def fark_bolgeleri(a, b):
    """İki gri kare arasındaki BÜYÜK ve TOPLU farklar. BİREBİR sahne_degisim.py:fark_bolgeleri.

    Küçük/dağılmış farklar (yaprak, rüzgâr, gürültü) alan eşiği + açma/kapama ile elenir;
    kare geneli değişim (ışık/kamera) ayrıca elenir.
    -> [{"kutu": [x1,y1,x2,y2], "alan": oran}]
    """
    a = cv2.GaussianBlur(a, (5, 5), 0)
    b = cv2.GaussianBlur(b, (5, 5), 0)
    d = cv2.absdiff(a, b)
    _, th = cv2.threshold(d, FARK_ESIK, 255, cv2.THRESH_BINARY)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(th, 8)
    toplam = a.shape[0] * a.shape[1]
    out = []
    for i in range(1, n):
        x, y, w, h, alan = stats[i]
        if alan / toplam < MIN_ALAN:
            continue
        if w > a.shape[1] * KARE_GENELI and h > a.shape[0] * KARE_GENELI:
            continue                                   # kare geneli: ışık/kamera
        out.append({"kutu": [int(x), int(y), int(x + w), int(y + h)],
                    "alan": float(alan / toplam)})
    return out


def ortus(k1, k2):
    """Kesişim / KÜÇÜK kutunun alanı. BİREBİR sahne_degisim.py:ortus."""
    ax1, ay1, ax2, ay2 = k1
    bx1, by1, bx2, by2 = k2
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    if ix * iy == 0:
        return 0.0
    return ix * iy / min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))


def kalici_degisimler(cam=None, arsiv_=None, yaz=True):
    """Ardışık günler arasında KALICI değişen bölgeleri bul. BİREBİR sahne_degisim.py:main.

    cam : tek kamera (1..5) ya da None → hepsi
    KALICILIK ŞARTI: değişim günün BİRDEN ÇOK saatinde görünmeli (geçici değil) —
    kaç saat gerektiği: max(2, len(SAATLER) - 1) = 3.

    -> [{"cam","gun_once","gun_sonra","kutu","alan","saat_sayisi"}]
    """
    kamlar = [int(cam)] if cam else [1, 2, 3, 4, 5]
    bulgular = []
    for c in kamlar:
        G = kareler(c, arsiv_)
        gunler = sorted(G)
        if len(gunler) < 3:
            continue
        if yaz:
            print("\n=== kamera%d · %d gun ===" % (c, len(gunler)), flush=True)
        for gi in range(1, len(gunler)):
            g0, g1 = gunler[gi - 1], gunler[gi]
            aday = collections.defaultdict(list)        # kutu-imzası -> [(saat, alan)]
            for sa in SAATLER:
                p0, p1 = en_yakin(G[g0], sa), en_yakin(G[g1], sa)
                if not p0 or not p1:
                    continue
                a, b = oku(p0), oku(p1)
                if a is None or b is None or a.shape != b.shape:
                    continue
                b2, _sh = hizala(a, b)
                if b2 is None:
                    continue                            # kamera oynamış
                for r in fark_bolgeleri(a, b2):
                    ana = None
                    for k in aday:
                        # ⚠ eski kod burada eval(k) kullanıyordu; json.loads AYNI listeyi
                        #   üretir (anahtar str([int,...]) = geçerli JSON) — davranış birebir.
                        if ortus(json.loads(k), r["kutu"]) > ORTUS_ESIK:
                            ana = k
                            break
                    aday[ana or str(r["kutu"])].append((sa, r["alan"]))
            for k, v in aday.items():
                if len(v) < max(2, len(SAATLER) - 1):
                    continue                            # KALICILIK şartı
                kutu = json.loads(k)
                bulgular.append({"cam": c, "gun_once": g0, "gun_sonra": g1,
                                 "kutu": kutu,
                                 "alan": float(np.mean([x[1] for x in v])),
                                 "saat_sayisi": len(v)})
                if yaz:
                    print("  %s → %s  kutu %s  alan %.4f  (%d saatte de var)"
                          % (g0, g1, kutu, np.mean([x[1] for x in v]), len(v)), flush=True)
    if yaz:
        print("\nTOPLAM KALICI DEGISIM: %d" % len(bulgular))
        print("kamera dagilimi:", dict(collections.Counter(b["cam"] for b in bulgular)))
    return bulgular


# ==========================================================================
#  AN DARALTMA  (degisim_anlari.py)
# ==========================================================================
def bolge_imza(g, kutu):
    """Bölgenin IŞIKTAN ARINDIRILMIŞ yapı imzası. BİREBİR degisim_anlari.py:bolge_imza.

    ⚠ TUZAK (c): ham piksel farkı ışığa çok duyarlı — şafakta birkaç dakikalık kayma bile
      devasa fark üretiyordu ve "değişim anı" hep gün doğumuna düşüyordu (iki koşuda da).
      Çözüm: bölgeyi SIFIR-ORTALAMA / BİRİM-SAPMA yap → parlaklık ve kontrast farkı silinir,
      geriye YAPI kalır. Nesne girip çıkması yapıyı değiştirir, ışık değiştirmez.
      std < 3.0 → düz/karanlık bölge: yapı yok, güvenilmez, None.
    """
    x1, y1, x2, y2 = kutu
    r = g[max(0, y1):y2, max(0, x1):x2]
    if r.size == 0:
        return None
    r = cv2.GaussianBlur(r, (5, 5), 0).astype(np.float32)
    s = float(r.std())
    if s < IMZA_MIN_STD:
        return None
    return (r - float(r.mean())) / s


def fark(a, b):
    """İki imza arasındaki ortalama mutlak fark. BİREBİR degisim_anlari.py:fark."""
    if a is None or b is None or a.shape != b.shape:
        return None
    return float(np.mean(np.abs(a - b)))


def _ref_gun(gun_once):
    """SABİT referans günü = g0'dan BİR ÖNCEKİ gün. TUZAK (b)'nin çözümü."""
    d = _dt.date(int(gun_once[:4]), int(gun_once[4:6]), int(gun_once[6:8])) - _dt.timedelta(days=1)
    return d.strftime("%Y%m%d")


def an_daralt(bulgu, arsiv_=None):
    """Kalıcı bir değişimin ANINI daralt. BİREBİR degisim_anlari.py:main'in döngü gövdesi.

    ⚠ TUZAK (a): referans önceki günün GECE karesi olursa an HEP gün doğumuna düşer.
      Bu yüzden her kare, referans günün AYNI SAATİNDEKİ karesiyle kıyaslanır (±10 dk).
    ⚠ TUZAK (b): referans "bir önceki gün" olursa, değişim g0 içinde olduysa g1'in İLK
      karesinde bile fark yüksek çıkar ve an daraltılamaz (ARABA BÖYLE KAÇTI). Bu yüzden
      referans SABİT: g0'dan bir önceki gün; seri g0+g1 boyunca kurulur.
    ⚠ An SADECE kararlı ışık saatlerinde (07:00-19:00) aranır. Dışarıda kalan değişim için
      pencere kaba kalır — ama yanlış "şafak" bulgusu üretmekten iyidir.

    -> {"cam","gun","dk","pencere","ts","kutu","alan","kare"} | None
    """
    cam, g1 = bulgu["cam"], bulgu["gun_sonra"]
    kutu = bulgu["kutu"]
    kareler_ = arsiv.gun_kareleri(cam, g1, arsiv_)
    onceki = arsiv.gun_kareleri(cam, bulgu["gun_once"], arsiv_)
    if len(kareler_) < 6 or not onceki:
        return None

    ref_list = arsiv.gun_kareleri(cam, _ref_gun(bulgu["gun_once"]), arsiv_)
    if len(ref_list) < MIN_REF_KARE:
        return None                                    # referans gün yoksa bu bulguyu atla
    ref_map = {dk: p for dk, p in ref_list}
    ref_dks = sorted(ref_map)

    def ref_es(dk):
        en = min(ref_dks, key=lambda x: abs(x - dk))
        return ref_map[en] if abs(en - dk) <= 10 else None

    seri = []
    for gun_i, (gun_ad, liste) in enumerate(((bulgu["gun_once"], onceki), (g1, kareler_))):
        for dk, p in liste:
            if not (GUNDUZ_BAS_DK <= dk <= GUNDUZ_BIT_DK):
                continue
            q = ref_es(dk)
            if not q:
                continue
            d = fark(bolge_imza(oku(q), kutu), bolge_imza(oku(p), kutu))
            if d is not None:
                seri.append((gun_i * 1440 + dk, d, p, gun_ad, dk))
    if len(seri) < MIN_SERI:
        return None

    d0 = np.median([s[1] for s in seri[:6]])           # referansa göre BAŞLANGIÇ seviyesi
    dz = np.median([s[1] for s in seri[-6:]])          # bitiş seviyesi
    if dz - d0 < YUKSELIS_MIN:
        return None                                    # net bir kalıcı yükseliş yok
    esik = d0 + (dz - d0) * YUKSELIS_ORAN
    an = None
    for i in range(len(seri) - 3):
        if all(seri[i + k][1] >= esik for k in range(KALICI_KARE)):
            an = i
            break
    if an is None:
        return None

    _, _, p, gun_ad, dk = seri[an]
    onc = seri[max(0, an - 1)]
    ts = int(_dt.datetime(int(gun_ad[:4]), int(gun_ad[4:6]), int(gun_ad[6:8]),
                          dk // 60, dk % 60, tzinfo=arsiv.TZ).timestamp() * 1000)
    return {"cam": cam, "gun": gun_ad, "dk": dk,
            "pencere": "%s %02d:%02d → %02d:%02d" % (gun_ad, onc[4] // 60, onc[4] % 60,
                                                     dk // 60, dk % 60),
            "ts": ts, "kutu": kutu, "alan": bulgu["alan"], "kare": p}


# ==========================================================================
#  OLAY KAYDIYLA KIYAS
# ==========================================================================
def insan_zamanlari(olaylar=None):
    """Olay kaydındaki İNSAN tespitlerinin zaman damgaları (sıralı).
    BİREBİR degisim_anlari.py:85-86 — det_ts varsa o, yoksa ts. RETRO DA SAYILIR:
    geçmişe dönük tespit de "o an biri vardı" bilgisidir, kaçırmayı açıklar."""
    from . import olay as _olay
    ev = _olay.olaylari_cek() if olaylar is None else _olay._ev_listesi(olaylar)
    return sorted(int(e.get("det_ts") or e.get("ts")) for e in ev if e.get("kind") == "person")


def olayla_kiyasla(anlar, olaylar=None, yakin_dk=YAKIN_DK, yaz=True):
    """Her değişim anı için: o pencerede insan tespiti var mı?
    BİREBİR degisim_anlari.py'nin `aciklandi` mantığı. YOKSA → KANITLANMIŞ KAÇIRMA.

    -> {"bulgu": [...], "aciklanamayan": [...]}
    """
    kisiler = insan_zamanlari(olaylar)
    if yaz:
        print("olay kaydinda insan tespiti: %d" % len(kisiler), flush=True)
    bulgu = []
    for x in anlar:
        if not x:
            continue
        yakin = [t for t in kisiler if abs(t - x["ts"]) <= yakin_dk * 60 * 1000]
        bulgu.append(dict(x, aciklandi=bool(yakin), yakin_olay=len(yakin)))
    kac = [x for x in bulgu if x["aciklandi"] is False]
    if yaz:
        print("\nANI BULUNAN DEGISIM: %d" % len(bulgu))
        print("  olayla ACIKLANAN  : %d" % (len(bulgu) - len(kac)))
        print("  ACIKLANAMAYAN     : %d   ← kanitlanmis kacirma adayi" % len(kac))
        for x in sorted(kac, key=lambda z: -z["alan"])[:15]:
            print("   kamera%d  %s  %s  alan %.4f"
                  % (x["cam"], x["gun"], x["pencere"], x["alan"]))
        print("\nkamera dagilimi (aciklanamayan): %s"
              % dict(collections.Counter(x["cam"] for x in kac)))
    return {"bulgu": bulgu, "aciklanamayan": kac}


def calistir(cam=None, olaylar=None, yaz_sahne=None, yaz_anlar=None, yaz=True):
    """Tam zincir: kalıcı değişim → an daraltma → olay kıyası.
    sahne_degisim.py + degisim_anlari.py ardışık çalıştırmasının tek çağrılık hâli."""
    bul = kalici_degisimler(cam=cam, yaz=yaz)
    if yaz_sahne:
        with open(yaz_sahne, "w") as f:
            json.dump({"bulgular": bul,
                       "parametre": {"MIN_ALAN": MIN_ALAN, "SAATLER": SAATLER}},
                      f, indent=1, default=float)
    anlar = [a for a in (an_daralt(b) for b in bul) if a]
    r = olayla_kiyasla(anlar, olaylar, yaz=yaz)
    if yaz_anlar:
        with open(yaz_anlar, "w") as f:
            json.dump(r, f, indent=1, default=float)
    return {"kalici": bul, **r}


def kayitli(yaz=True):
    """Diskteki önceki koşunun sonucu (gate/sahne_degisim.json + degisim_anlari.json).
    Yeniden ölçmeden bakmak için — bu tarama tüm timeline'ı okur, ucuz değildir."""
    out = {}
    for ad, p in (("kalici", SAHNE_JSON), ("anlar", ANLAR_JSON)):
        if os.path.exists(p):
            with open(p) as f:
                out[ad] = json.load(f)
        else:
            out[ad] = None
    if yaz:
        k = (out["kalici"] or {}).get("bulgular", [])
        a = (out["anlar"] or {}).get("bulgu", [])
        kac = (out["anlar"] or {}).get("aciklanamayan", [])
        print("kalici degisim %d · ani bulunan %d · aciklanamayan %d" % (len(k), len(a), len(kac)))
        print("kamera dagilimi (kalici): %s" % dict(collections.Counter(x["cam"] for x in k)))
    return out


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "kayitli":
        kayitli()
    elif a[0] == "calistir":
        cam = int(a[1]) if len(a) > 1 else None
        calistir(cam=cam)
    else:
        print(__doc__)

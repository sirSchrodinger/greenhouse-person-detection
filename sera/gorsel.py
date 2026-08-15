# -*- coding: utf-8 -*-
"""
sera.gorsel — kırpma / normalizasyon / kutu çizimi / kontakt sayfası (2 Ağu 2026).

DEVRALINAN (mantık BİREBİR korundu, sayı kaymadı):
  kirp()        ← oof_sweep.py:34 · train_verifier3.py:47 · hacim_kuru.py:31 ·
                  hacim_diag.py:37 · olay_denetim2.py:46 · etiket_denetim.py:30
                  (aynı 17 satır 6 dosyada kopyalanmıştı)
  hazirla()     ← oof_sweep.py:51 · train_verifier3.py:64 · hacim_kuru.py:48 · olay_tara2.py:101
  baglam_kes()  ← retro_pano.py:hucre · retro_pano2.py:hucre · retro_zoom.py:hucre · olay_pano.py:hucre
  kutu_ciz()    ← retro_pano2.py:hucre içindeki cv2.rectangle
  hucre()       ← retro_pano2.py:hucre (en zengin varyant) + diğer üçünün geometrisi ön ayar olarak
  kontakt()     ← retro_pano.py:main · retro_pano2.py:main · olay_pano.py:pano (üç kopya birleştirildi)

BU DOSYA TOKEN TASARRUFUNUN ARACI: 30 görsele tek tek bakmak yerine TEK grid.
Bir kontakt sayfası ~1 görsel maliyetinde 25-48 kareyi gösterir.
"""
import os

import numpy as np
import cv2

from . import ayar

# ImageNet istatistikleri — ayar.py'den, np dizisine bir kez çevrilir
IMN = np.array(ayar.IMN, np.float32)
IMS = np.array(ayar.IMS, np.float32)

# yazı ayarları — retro_pano2.py:hucre ile aynı
FONT = cv2.FONT_HERSHEY_SIMPLEX
YAZI_BOY = 0.40
SATIR_YUK = 14
YAZI_RENK = (255, 255, 255)
KUTU_RENK = (0, 230, 255)          # kontakt sayfalarındaki turuncu-sarı çerçeve
BASLIK_RENK = (0, 255, 255)
CERCEVE_RENK = (70, 70, 70)


# ==========================================================================  kırpma
def kirp(img, box, pad=None, w=None, h=None):
    """Kutu çevresine PAD payı ver, letterbox'la KIRP_W×KIRP_H tuvale otur.

    BİREBİR: oof_sweep.py:kirp / train_verifier3.py:kirp / hacim_kuru.py:kirp.
    Doğrulayıcının gördüğü tek girdi budur — bir piksel kayması tüm skorları kaydırır,
    o yüzden burada hiçbir şey "temizlenmedi".

    img : BGR uint8 (cv2.imread çıktısı)
    box : [x1, y1, x2, y2] — orijinal kare koordinatlarında
    -> (KIRP_H, KIRP_W, 3) uint8  ·  kutu çok küçük/dışarıdaysa None
    """
    PAD = ayar.PAD if pad is None else pad
    W = ayar.KIRP_W if w is None else w
    H = ayar.KIRP_H if h is None else h
    x1, y1, x2, y2 = box
    bw, bh = max(2.0, x2 - x1), max(2.0, y2 - y1)
    x1 -= bw * PAD; x2 += bw * PAD; y1 -= bh * PAD; y2 += bh * PAD
    Hh, Ww = img.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(Ww, int(x2)), min(Hh, int(y2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    c = img[y1:y2, x1:x2]
    r = min(W / c.shape[1], H / c.shape[0])
    nw, nh = max(1, int(c.shape[1] * r)), max(1, int(c.shape[0] * r))
    tuval = np.zeros((H, W, 3), np.uint8)
    tuval[(H - nh) // 2:(H - nh) // 2 + nh, (W - nw) // 2:(W - nw) // 2 + nw] = cv2.resize(c, (nw, nh))
    return tuval


def hazirla(c, giris=None):
    """Kırpmayı gövdenin beklediği tensöre çevir: GIRIS×GIRIS, BGR→RGB, /255, ImageNet norm, CHW.

    BİREBİR: oof_sweep.py:hazirla / train_verifier3.py:hazirla / hacim_kuru.py:hazirla.
    -> (3, GIRIS, GIRIS) float32   (batch boyutu YOK — çağıran `[None]` ekler)
    """
    G = ayar.GIRIS if giris is None else giris
    x = cv2.resize(c, (G, G))
    x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return np.transpose((x - IMN) / IMS, (2, 0, 1))


def kirp_hazirla(img, box):
    """kirp + hazirla tek çağrıda. Kutu kırpılamazsa None.
    Doğrulayıcı hattının tek satırlık girişi: sess.run(..., {ad: kirp_hazirla(img, box)[None]})"""
    c = kirp(img, box)
    return None if c is None else hazirla(c)


# ==========================================================================  çizim
def kutu_ciz(img, box, renk=KUTU_RENK, kalinlik=2, kopya=False):
    """Kareye kutu çiz. Kaynak: retro_pano2.py:hucre / retro_pano.py:hucre.

    kopya=False (varsayılan) → YERİNDE çizer ve aynı diziyi döndürür; eski kod da
    kırpmayı `.copy()` ile aldıktan sonra yerinde çiziyordu. Önbellekten gelen bir
    kareye çizecekseniz kopya=True verin.
    """
    if img is None or box is None:
        return img
    t = img.copy() if kopya else img
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(t, (x1, y1), (x2, y2), renk, kalinlik)
    return t


# cv2'nin Hershey fontu SADECE ASCII basar; Türkçe harf "?" olarak çıkar (ilk koşuda
# başlık "sera.gorsel.kontakt ??? 12 var" göründü). Etiketlerimiz Türkçe olduğu için
# katlama zorunlu — bozuk karakter yerine okunur harf.
_KATLA = str.maketrans({
    "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U", "ş": "s", "Ş": "S",
    "ı": "i", "İ": "I", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    "—": "-", "–": "-", "·": ".", "≥": ">=", "≤": "<=", "→": "->", "←": "<-",
    "⚠": "!", "“": '"', "”": '"', "’": "'",
})


def ascii_katla(t):
    """Türkçe/tipografik karakterleri ASCII'ye katla (cv2.putText Hershey sınırı)."""
    return str(t).translate(_KATLA).encode("ascii", "replace").decode("ascii")


def yazi_bas(img, satirlar, x=4, y0=13, boy=YAZI_BOY, adim=SATIR_YUK, renk=YAZI_RENK):
    """Sol üste çok satırlı etiket. Kaynak: retro_pano2.py:hucre son döngüsü."""
    for i, t in enumerate(satirlar or ()):
        cv2.putText(img, ascii_katla(t), (x, y0 + adim * i), FONT, boy, renk, 1, cv2.LINE_AA)
    return img


# ==========================================================================  bağlam kırpması
def baglam_kes(img, box, mod="pano", kat=None):
    """Kutunun ÇEVRESİNİ de alan bağlam kırpması (kontakt sayfası hücresi için).

    Üç geometri de eski dosyalardan BİREBİR — hangisini kullandığınız hücrenin ne kadar
    "yakın" göründüğünü belirler, karar bu yüzden değişir; karışmasın diye adlandırıldı:
      "pano" ← retro_pano.py / retro_pano2.py : yari = max(bw, bh*0.55) * 1.9, dikey ×1.15
      "zoom" ← retro_zoom.py                  : yw = bw*1.25 + 6, yh = bh*1.25 + 6
      "kare" ← olay_pano.py                   : yari = max(bw, bh) * 1.1, kare pencere

    -> (kes, (a, c))  ·  a,c = kesitin sol-üst köşesi (kutuyu kesit içinde çizmek için)
    """
    Hh, Ww = img.shape[:2]
    if not box:
        return img, (0, 0)
    x1, y1, x2, y2 = [int(v) for v in box]
    if mod == "zoom":
        k = 1.25 if kat is None else kat
        bw, bh = max(6, x2 - x1), max(6, y2 - y1)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        yw, yh = int(bw * k) + 6, int(bh * k) + 6
        a, b = max(0, cx - yw), min(Ww, cx + yw)
        c, d = max(0, cy - yh), min(Hh, cy + yh)
    elif mod == "kare":
        k = 1.1 if kat is None else kat
        bw, bh = max(8, x2 - x1), max(8, y2 - y1)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        yari = int(max(bw, bh) * k)
        a, b = max(0, cx - yari), min(Ww, cx + yari)
        c, d = max(0, cy - yari), min(Hh, cy + yari)
    else:                                     # "pano"
        k = 1.9 if kat is None else kat
        bw, bh = max(8, x2 - x1), max(8, y2 - y1)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        yari = int(max(bw, bh * 0.55) * k)
        a, b = max(0, cx - yari), min(Ww, cx + yari)
        c, d = max(0, cy - int(yari * 1.15)), min(Hh, cy + int(yari * 1.15))
    kes = img[c:d, a:b]
    if kes.size == 0:
        return img, (0, 0)
    return kes.copy(), (a, c)


# ==========================================================================  hücre
def hucre(kaynak, box=None, ust=(), mod="pano", w=None, h=None, ust_bant=None,
          kat=None, cerceve=True, interp=cv2.INTER_CUBIC, zemin=0):
    """Kontakt sayfasının TEK hücresi: bağlam kırpması + kutu + etiket satırları.

    Kaynak: retro_pano2.py:hucre (birleştirilmiş hâl). retro_pano.py/retro_zoom.py/
    olay_pano.py varyantları `mod` + ayar.HUCRE_ONAYAR ile karşılanır.

    kaynak : dosya yolu (str) VEYA hazır BGR dizi
    box    : [x1,y1,x2,y2] veya None (kutu yoksa tüm kare küçültülür)
    ust    : hücrenin sol üstüne basılacak etiket satırları
    mod    : "pano" | "zoom" | "kare" | "kucuk"  (bkz. baglam_kes / ayar.HUCRE_ONAYAR)
    -> (h, w, 3) uint8
    """
    on = ayar.HUCRE_ONAYAR.get(mod, ayar.HUCRE_ONAYAR["pano"])
    W = on["w"] if w is None else w
    H = on["h"] if h is None else h
    U = on["ust"] if ust_bant is None else ust_bant
    geo = "pano" if mod == "kucuk" else mod
    K = on["kat"] if kat is None else kat

    img = cv2.imread(kaynak) if isinstance(kaynak, str) else kaynak
    if img is None:
        c = np.full((H, W, 3), zemin, np.uint8)
        cv2.putText(c, "KARE YOK", (10, H // 2), FONT, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
        # kaynak: retro_pano2.py:hucre — "KARE YOK" hücresi ATLANMAZ, gösterilir.
        # Sessizce düşen kare, ızgarada sayım kaymasına ve yanlış "temiz liste" hükmüne yol açar.
        yazi_bas(c, ust, boy=YAZI_BOY, adim=SATIR_YUK)
        return c

    kes, (a, c0) = baglam_kes(img, box, geo, K)
    if box is not None and kes is not img:
        x1, y1, x2, y2 = [int(v) for v in box]
        cv2.rectangle(kes, (x1 - a, y1 - c0), (x2 - a, y2 - c0), KUTU_RENK, 2)

    r = min(W / kes.shape[1], (H - U) / kes.shape[0])
    kes = cv2.resize(kes, (max(1, int(kes.shape[1] * r)), max(1, int(kes.shape[0] * r))),
                     interpolation=interp)
    hc = np.full((H, W, 3), zemin, np.uint8)
    y0 = U + ((H - U) - kes.shape[0]) // 2
    x0 = (W - kes.shape[1]) // 2
    hc[y0:y0 + kes.shape[0], x0:x0 + kes.shape[1]] = kes
    yazi_bas(hc, ust)
    if cerceve:
        cv2.rectangle(hc, (0, 0), (W - 1, H - 1), CERCEVE_RENK, 1)
    return hc


# ==========================================================================  kontakt sayfası
def kontakt(hucreler, cikti, sutun=None, baslik=None, kalite=None, zemin=0, numarala=False):
    """Hücreleri ızgaraya diz, tek JPEG yaz. Satır sayısı OTOMATİK.

    Kaynak: retro_pano.py:main + retro_pano2.py:main + olay_pano.py:pano (üç kopya birleşti).
    Hücreler farklı boyutta olabilir (eski kopyalar hepsini eşit varsayıyordu); ızgara
    en büyük hücreye göre kurulur, eşit boyutta sonuç eskisiyle aynıdır.

    hucreler : hucre() çıktısı dizilerin listesi
    cikti    : yazılacak .jpg yolu
    -> yazılan yol (hücre yoksa None)
    """
    hucreler = [h for h in hucreler if h is not None]
    if not hucreler:
        print("kontakt: hücre yok →", cikti)
        return None
    S = ayar.SUTUN if sutun is None else int(sutun)
    S = max(1, min(S, len(hucreler)))
    Q = ayar.JPEG_KALITE if kalite is None else int(kalite)
    ch = max(h.shape[0] for h in hucreler)
    cw = max(h.shape[1] for h in hucreler)
    bant = ayar.BASLIK_BANT if baslik else 0
    satir = (len(hucreler) + S - 1) // S

    pano = np.full((bant + satir * ch, S * cw, 3), zemin, np.uint8)
    if baslik:
        cv2.putText(pano, ascii_katla(baslik), (8, bant - 11), FONT, 0.62,
                    BASLIK_RENK, 1, cv2.LINE_AA)
    for i, hc in enumerate(hucreler):
        y = bant + (i // S) * ch
        x = (i % S) * cw
        pano[y:y + hc.shape[0], x:x + hc.shape[1]] = hc
        if numarala:
            # koyu zemin şart: numara doğrudan görüntünün üstüne basılınca açık karelerde okunmuyor
            cv2.rectangle(pano, (x + cw - 46, y + ch - 20), (x + cw - 4, y + ch - 3), (0, 0, 0), -1)
            cv2.putText(pano, "#%02d" % (i + 1), (x + cw - 43, y + ch - 7), FONT, 0.45,
                        (200, 200, 200), 1, cv2.LINE_AA)
    d = os.path.dirname(os.path.abspath(cikti))
    if d:
        os.makedirs(d, exist_ok=True)
    cv2.imwrite(cikti, pano, [int(cv2.IMWRITE_JPEG_QUALITY), Q])
    print("YAZILDI %s  %s  (%d hucre / %d sutun / %d satir)" %
          (cikti, pano.shape, len(hucreler), S, satir))
    return cikti


def kontakt_kayitlar(kayitlar, cikti, mod="pano", sutun=None, baslik=None,
                     yol_al=None, kutu_al=None, etiket_al=None, kalite=None):
    """Kayıt listesinden doğrudan kontakt sayfası. Hücre kurma zahmetini kaldırır.

    kayitlar  : dict listesi
    yol_al    : kayıt -> görsel yolu     (varsayılan: r["p"] veya r["yol"] veya r["kare"])
    kutu_al   : kayıt -> [x1,y1,x2,y2]   (varsayılan: r["box"] veya r["kutu"])
    etiket_al : kayıt -> etiket satırları (varsayılan: kısa özet)
    """
    def _yol(r):
        for k in ("p", "yol", "kare", "path"):
            if r.get(k):
                v = r[k]
                return v if os.path.isabs(v) else os.path.join(ayar.ARSIV, v)
        return None

    def _kutu(r):
        return r.get("box") or r.get("kutu") or r.get("pbox")

    def _et(r):
        s1 = "k%s %s" % (r.get("cam", "?"), (r.get("zaman") or r.get("saat") or "")[:8])
        d, g = r.get("det"), (r.get("dog") if r.get("dog") is not None else r.get("dog_oof"))
        s2 = "det %s  dog %s" % ("%.2f" % d if d is not None else "-",
                                 "%.2f" % g if g is not None else "-")
        return [s1, s2]

    yol_al = yol_al or _yol
    kutu_al = kutu_al or _kutu
    etiket_al = etiket_al or _et
    hs = [hucre(yol_al(r), kutu_al(r), etiket_al(r), mod=mod) for r in kayitlar]
    return kontakt(hs, cikti, sutun=sutun or ayar.HUCRE_ONAYAR.get(mod, {}).get("sutun"),
                   baslik=baslik, kalite=kalite, numarala=True)

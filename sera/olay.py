# -*- coding: utf-8 -*-
"""
sera.olay — CANLI OLAY KAYDININ DENETİMİ ve YANLIŞ ALARM TEMİZLİĞİ (2 Ağu 2026).

Devralınan dosyalar (mantık korunarak birleştirildi, her fonksiyonun kaynağı docstring'inde):
    olay_denetim.py    — LOEO/LOCO fold-dışı skorlama + 119 etiketli olayla eşik kalibrasyonu
    olay_denetim2.py   — çizim/pre-roll tuzaklarını ele alan yeniden tarama
    olay_tara.py       — faz 1 gömü üretimi (top-3 kutu, IoU baskılama)
    olay_tara2.py      — faz 1b: ÇİZİMDEN ARINDIRILMIŞ kanıt karesi üretimi
    olay_karar.py      — kayıtlı skorları kalibre eşikle yeniden bölme
    cizim_geri_al.py   — kırmızı bbox maskesi, kutu kurtarma, inpaint temizliği
    olay_temizle.py    — state.json'dan yanlış olay silme (yedek + geri-al + yarış koruması)


╔══════════════════════════════════════════════════════════════════════════════╗
║ BULGU — ŞÜPHELİ KAPISI DOĞRULAYICIYI DEVRE DIŞI BIRAKIYOR                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
    vps/person_watch_v3.py:1033   `if do_fire and _verifier is not None and det_box:`

Şüpheli kapıları (hd-red / tekrar-statik / cok-olcek) ateşi kestiğinde `do_fire` False olur
ve DOĞRULAYICI HİÇ ÇALIŞMAZ. AUC 0.98'lik model tam gerektiği yerde devre dışı kalır.

ÖLÇÜLDÜ (iki bağımsız protokol — fold-dışı OOF ve olay-dışla LOEO — aynı sonucu verdi):
doğrulayıcı >= 0.50 ile ateşlenseydi 14 GERÇEK insan kurtulur, 0 yanlış geçerdi.
Skorlar çakışmıyor bile: gerçekler 0.76-1.00, yanlış/belirsizler 0.001-0.35.
En zararlı kapı `tekrar-statik`: 7 olayın 6'sı gerçek insandı.
`hd-grab-yok` kurtarma listesinde DEĞİL — orada 0 gerçek insan çıktı ve o kapı fail-closed
güvenlik kuralıdır (hakem cevap veremediyse ateşleme).

⚠ SAYI FARKI, İKİSİ DE KAYITTA (uydurma yok, ikisini de yazıyoruz):
    · 14 → vps/person_watch_v3.py:1049 yorumu + bu turun brifingi (35 şüpheli olay denetimi)
    · 16 → gate/olay_karar.json:supheli_kapisi, hd-grab-yok hariç "gercek" toplamı
      (hd-red 6 · tekrar-statik 6 · cok-olcek 2 · cok_olcek 2)
  Fark muhtemelen havuz/eşik farkı. `kapi_bulgusu()` ikisini de raporlar.

⚠ DÜZELTMENİN DURUMU — SSH ile SALT-OKUMA ÖLÇÜLDÜ, iki kez, ve ARADA DEĞİŞTİ:
    · 2 Ağu 17:12 TR : VPS kopyasında VER_KURTAR YOK (md5 90456ee6…), yerelde VAR → açık
    · 2 Ağu 17:37 TR : VPS kopyası yerelle AYNI (md5 ce6b1039…), VER_KURTAR 13 satır.
                       /opt/sera/person_watch_v3.py mtime 14:23:37 UTC,
                       sera-person-canary restart 14:24:55 UTC → dosya güncellendikten
                       SONRA yeniden başlatılmış, yani kurtarma bloğu CANLIDA ÇALIŞIYOR.
  ⚠ AMA SADECE KAMERA5'TE: `sera-person-canary` (PCAMS=kamera5) person_watch_v3.py'yi
    koşan TEK aktif servis. `sera-person` hâlâ eski /opt/sera/person_watch.py'yi koşuyor
    ve o dosya doğrulayıcıyı HİÇ kullanmıyor (grep -c verifier = 0) → kamera1-4'te ne
    doğrulayıcı ne de kurtarma var.
  Bu satırlar ÖLÇÜM ANININ fotoğrafıdır; güncel durumu `sera.dagit.durum()` söyler.


ÜÇ TUZAK (üçü de bu projede yaşandı — kod bunları ele alır, yorumlar korunur)
  1. PRE-ROLL   : olayın 1.jpg'si tespit anından ~POLL_S(20) sn ÖNCESİDİR; kişi kadrajda
                  olmayabilir. KARAR OLAYIN TÜM KARELERİNİN EN İYİSİYLE VERİLİR.
  2. ÇİZİM      : `N.jpg` kareleri canlı sistemin KIRMIZI BBOX ÇİZDİĞİ karelerdir. Çizim
                  dedektörü öldürüyor — 47 çift karede ölçüldü: ham karede 0.35'i geçen 37
                  tespitin çizili karede sadece 21'i geçiyor. `N_raw.jpg` varsa o kullanılır,
                  yoksa `cizim_temizle()` inpaint'ler. Çizilen dikdörtgen CANLI SİSTEMİN
                  GÖRDÜĞÜ KUTUDUR — bedava etiket, yedek kutu olarak eklenir.
  3. TAUTOLOJİ  : karar eşiği KAFADAN atılmaz. `kalibre()` bağımsız TP/FP etiketleriyle,
                  `ayar.yanlis_esik()` fold-dışı OOF skorlarıyla türetir.

Kullanım:
    from sera import olay
    ev  = olay.olaylari_cek(45)          # ev_now.json ya da API
    kov = olay.denetle(ev)               # VARSA kayıtlı denetimi okur, yeniden ölçmez
    olay.temizle([r["id"] for r in kov["yanlis"]])          # KURU (hiçbir şey yazmaz)
"""
import os
import re
import json
import time
import glob
import shutil
import subprocess
import collections

import numpy as np
import cv2

from . import ayar
from . import arsiv
from . import gorsel

# ============================================================================ sabitler
ARSIV = ayar.ARSIV
GATE = ayar.GATE
SCRATCH = ayar.SCRATCH

# kaynak: olay_denetim.py:98 · olay_tara.py:22 · olay_denetim2.py:207 (aynı yol 6 dosyada)
EV_JSON = os.path.join(SCRATCH, "ev_now.json")
# kaynak: degisim_anlari.py:81 — tek API çağrısı; çerez orada açıkta duruyordu
API_URL = os.environ.get("SERA_API_URL", "https://sera.sirschrodinger.com/api/events")
API_CEREZ = os.environ.get("SERA_API_CEREZ", "sera_ev=e9f3a2c17b40d")

# denetim çıktıları — ÖNCELİK SIRASI (denetle() bu sırayla arar)
KARAR_JSON = os.path.join(GATE, "olay_karar.json")        # olay_karar.py  (kalibre eşik)
DENETIM_JSON = os.path.join(GATE, "olay_denetim.json")    # olay_denetim.py (LOEO)
DENETIM2_JSON = os.path.join(GATE, "olay_denetim2.json")  # olay_denetim2.py (v3 kafa)
SILINECEK_JSON = os.path.join(GATE, "silinecek.json")     # iki denetimin çelişkisiz kesişimi
KAYNAK_ONCELIK = (KARAR_JSON, DENETIM_JSON, DENETIM2_JSON)

# faz 1 gömü önbellekleri (olay_tara2.py çıktısı) — LOEO denetimi bunları okur
OLAY_GOMU2 = os.path.join(GATE, "olay_gomu2.npz")
OLAY_META2 = os.path.join(GATE, "olay_meta2.json")
OLAY_GOMU = os.path.join(GATE, "olay_gomu.npz")           # faz 1 (çizimli — kullanma)
OLAY_META = os.path.join(GATE, "olay_meta.json")
HACIM_KURU = os.path.join(GATE, "hacim_kuru.json")        # timeline destek kanalı

# tarama sabitleri — kaynak: olay_tara.py:30-36 / olay_tara2.py:33-36 (ikisinde de aynı)
DET_TABAN = ayar.DET_TARA          # 0.05 · kutu ÜRETME tabanı, ateşleme eşiği DEĞİL
DET_ESIK = ayar.DET_ESIK           # 0.03 · olay_denetim2.py:Motor.kutular varsayılanı
MIN_ALAN = ayar.MIN_ALAN           # 0.0018
TOP_K = 3                          # kare başına en fazla 3 aday kutu
IOU_BAS = 0.55                     # olay_tara*.py IoU baskılama eşiği
IPLIK_DENETIM = int(os.environ.get("SERA_IPLIK_DENETIM", "3"))   # olay_denetim2.py:Motor → 3

# çizim maskesi — kaynak: cizim_geri_al.py:kirmizi_maske (olay_tara2.py'de birebir aynı)
KIRMIZILIK = 45
KIRMIZI_R = 90
CIZIM_MIN_PIKSEL = 20

# kamera-dışı (LOCO) itiraz eşiği — kaynak: olay_temizle.py:T_LOCO
T_LOCO = 0.066
# state_service.EVENTS_CAP ile aynı — kaynak: olay_temizle.py:CAP
CAP = 4000
KOVALAR = ("yanlis", "gercek", "belirsiz", "kare_yok")

# state hedefleri — kaynak: olay_temizle.py:STATE_VARSAYILAN / EVIMG_DIR
STATE_CANLI = ayar.VPS_KOK.rstrip("/") + "/state.json"    # /opt/sera/state.json (UZAK)
STATE_PROVA = EV_JSON                                     # laptopta prova için anlık görüntü
EVIMG_DIR = ayar.VPS_KOK.rstrip("/") + "/events"

# şüpheli kapıları — ayar.py'de tanımlı, burada yeniden ihraç
SUPHELI_KAPILAR = ayar.SUPHELI_KAPILAR
# person_watch_v3.py:153 VER_KURTAR varsayılanı (hd-grab-yok BİLEREK yok)
VER_KURTAR = ("hd-red", "tekrar-statik", "cok-olcek", "cok_olcek")
VER_KURTAR_ESIK = ayar.DOG_ESIK      # 0.50 — canlı çalışma noktası


# ==========================================================================
#  ÇİZİM (cizim_geri_al.py + olay_tara2.py)
# ==========================================================================
def kirmizi_maske(img):
    """Canlı sistemin çizdiği KIRMIZI bbox piksellerinin maskesi.

    BİREBİR cizim_geri_al.py:kirmizi_maske (olay_tara2.py:kirmizi_maske ile de aynı).
    Ölçüt: R, hem G hem B'yi 45'ten fazla geçiyor VE R > 90.
    -> uint8 (0/1) maske
    """
    B = img[:, :, 0].astype(np.int16)
    G = img[:, :, 1].astype(np.int16)
    R = img[:, :, 2].astype(np.int16)
    kirmizilik = R - np.maximum(G, B)
    return ((kirmizilik > KIRMIZILIK) & (R > KIRMIZI_R)).astype(np.uint8)


def _cizim_kutusu_bilesen(img, min_kenar=5):
    """BİREBİR cizim_geri_al.py:cizim_kutusu — bağlantılı bileşen + 'içi boş çerçeve' şartı.

    Doğal kırmızı nesneyi (bidon, çatı, bayrak) ELEMEK için üç şart aranır:
      kenar_orani >= 0.75 (çizgi bileşenin kenarında mı) · doluluk <= 0.55 (içi dolu =
      doğal nesne) · en az 3 kenarın temsil edilmesi (kopuk çizgi değil).
    """
    m = kirmizi_maske(img)
    if m.sum() < CIZIM_MIN_PIKSEL:
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, np.ones((3, 3), np.uint8)), 8)
    en_iyi, en_skor = None, 0.0
    for k in range(1, n):
        x, y, w, h, ar = st[k]
        if w < min_kenar or h < min_kenar or ar < 12:
            continue
        sub = (lab[y:y + h, x:x + w] == k)
        kalinlik = max(2, int(round(min(w, h) * 0.12)))
        cerceve = np.zeros((h, w), bool)
        cerceve[:kalinlik, :] = True
        cerceve[-kalinlik:, :] = True
        cerceve[:, :kalinlik] = True
        cerceve[:, -kalinlik:] = True
        toplam = sub.sum()
        if toplam == 0:
            continue
        kenar_orani = float((sub & cerceve).sum()) / toplam
        doluluk = float(toplam) / (w * h)
        ust = sub[:kalinlik, :].any()
        alt = sub[-kalinlik:, :].any()
        sol = sub[:, :kalinlik].any()
        sag = sub[:, -kalinlik:].any()
        kenar_sayi = int(ust) + int(alt) + int(sol) + int(sag)
        if kenar_orani < 0.75 or doluluk > 0.55 or kenar_sayi < 3:
            continue
        skor = toplam * kenar_orani
        if skor > en_skor:
            en_skor = skor
            en_iyi = [int(x), int(y), int(x + w - 1), int(y + h - 1)]
    return en_iyi


def _cizim_kutusu_projeksiyon(img):
    """BİREBİR olay_tara2.py:cizim_kutusu — satır/sütun projeksiyonu.

    ÖLÇÜLDÜ: 47 çift (çizili + ham) karede medyan IoU 0.82, 32/47 kare IoU >= 0.7.
    Bileşen yönteminden daha toleranslı; çizgi kopuksa da kutuyu bulur.
    """
    m = kirmizi_maske(img)
    if m.sum() < CIZIM_MIN_PIKSEL:
        return None
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    Rw = m.sum(1).astype(float)
    Cw = m.sum(0).astype(float)
    if Rw.max() < 4 or Cw.max() < 4:
        return None
    ry = np.where(Rw >= 0.45 * Rw.max())[0]
    cx = np.where(Cw >= 0.45 * Cw.max())[0]
    if len(ry) < 2 or len(cx) < 2:
        return None
    k = [int(cx.min()), int(ry.min()), int(cx.max()), int(ry.max())]
    if k[2] - k[0] < 4 or k[3] - k[1] < 4:
        return None
    return k


def cizim_kutusu(img, yontem="bilesen", min_kenar=5):
    """Canlı sistemin ÇİZDİĞİ dikdörtgeni geri kazan (bedava kutu = sistemin gördüğü kutu).

    yontem="bilesen"     → cizim_geri_al.py yolu (doğal kırmızı nesneyi elemede sıkı)
    yontem="projeksiyon" → olay_tara2.py yolu (kopuk çizgide toleranslı, medyan IoU 0.82)

    ⚠ İKİ YÖNTEM DE KORUNDU çünkü ikisinin de geçmiş ölçümü var; hangisinin çağrıldığı
      sayıları değiştirir. Varsayılan "bilesen" — olay_denetim2.py bu yolu kullanıyordu.

    Maske isteniyorsa ayrıca kirmizi_maske(img) çağır: eski cizim_geri_al.cizim_kutusu
    (kutu, maske) döndürüyordu ve o maske TAM OLARAK kirmizi_maske(img)'in kendisiydi
    (dilate/CLOSE'dan ÖNCEKİ hâli) — bilgi kaybı yok.
    -> [x1, y1, x2, y2] | None
    """
    if img is None:
        return None
    if yontem == "projeksiyon":
        return _cizim_kutusu_projeksiyon(img)
    if yontem == "bilesen":
        return _cizim_kutusu_bilesen(img, min_kenar=min_kenar)
    raise ValueError("bilinmeyen yontem: %s (bilesen|projeksiyon)" % yontem)


def cizim_temizle(img, kutu=None):
    """Kırmızı çizgi piksellerini inpaint ile doldur; dedektör yeniden çalışabilsin.

    BİREBİR cizim_geri_al.py:temizle (olay_tara2.py:temizle ile aynı). Kutu verilirse
    SADECE kutunun çevresindeki şerit temizlenir — kutunun İÇİ (yani insanın kendisi)
    ve karenin geri kalanı el değmeden kalır.

    ⚠ Adı `cizim_temizle`: bu modüldeki `temizle()` state.json'dan olay silen fonksiyondur.
    """
    m = kirmizi_maske(img)
    if kutu is not None:
        koru = np.zeros(m.shape, np.uint8)
        x1, y1, x2, y2 = kutu
        pad = 4
        koru[max(0, y1 - pad):y2 + pad + 1, max(0, x1 - pad):x2 + pad + 1] = 1
        ic = np.zeros(m.shape, np.uint8)
        kal = max(2, int(round(min(x2 - x1, y2 - y1) * 0.12))) + pad
        ic[y1 + kal:max(y1 + kal, y2 - kal), x1 + kal:max(x1 + kal, x2 - kal)] = 1
        m = (m & koru & (1 - ic)).astype(np.uint8)
    if m.sum() == 0:
        return img
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    return cv2.inpaint(img, m, 3, cv2.INPAINT_TELEA)


def iou(a, b):
    """Standart IoU (kesişim/birleşim). BİREBİR cizim_geri_al.py:iou · olay_tara*.py:iou.
    ⚠ sera.dedektor'daki NMS ölçütü kesişim/KÜÇÜK-ALAN'dır; ikisi aynı sayı değildir."""
    if a is None or b is None:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    i = (x2 - x1) * (y2 - y1)
    A = (a[2] - a[0]) * (a[3] - a[1])
    B = (b[2] - b[0]) * (b[3] - b[1])
    return i / max(1e-6, float(A + B - i))


# ==========================================================================
#  OLAY KAYDI
# ==========================================================================
def _ev_listesi(d):
    """ev_now.json ({"events": [...]}) ya da düz liste — ikisini de kabul et."""
    if isinstance(d, dict):
        return d.get("events", [])
    return d if isinstance(d, list) else []


def olaylari_cek(gun=45, yol=None, api=False, yaz=None, zaman_asimi=25):
    """Güvenlik olay kaydını getir. Önce yerel anlık görüntü, gerekirse API.

    Kaynak: olay_denetim.py:98 (yerel ev_now.json) + degisim_anlari.py:78-84 (API yolu).

    gun          : API'den kaç günlük kayıt (?days=)
    yol          : belirli bir anlık görüntü dosyası; None → SCRATCH/ev_now.json
    api=True     : yerel dosya olsa bile ağdan çek
    yaz          : API'den çekilen kaydın yazılacağı yol (None → yazma)

    ⚠ AĞA ÇIKAR: api=True ya da yerel dosya yoksa. Sadece OKUMA yapar (GET), hiçbir
      süreci tetiklemez. 4G üstünden DVR indirmesiyle ilgisi yoktur.
    -> [olay, ...]   (TÜM olaylar: person + vehicle + pump; süzmek için person_olaylari())
    """
    p = yol or EV_JSON
    if not api and os.path.exists(p):
        with open(p) as f:
            return _ev_listesi(json.load(f))
    r = subprocess.run(["curl", "-s", "-m", str(int(zaman_asimi)),
                        "-H", "Cookie: " + API_CEREZ,
                        "%s?days=%d" % (API_URL, int(gun))],
                       capture_output=True, text=True)
    if r.returncode != 0 or not (r.stdout or "").strip():
        raise RuntimeError("olay kaydı çekilemedi (curl rc=%s, %s)"
                           % (r.returncode, (r.stderr or "")[:120]))
    d = json.loads(r.stdout)
    ev = _ev_listesi(d)
    if yaz:
        with open(yaz, "w") as f:
            json.dump(d, f)
        print("olay kaydı yazıldı: %s (%d olay)" % (yaz, len(ev)), flush=True)
    return ev


def person_olaylari(olaylar):
    """kind=='person' VE retro olmayan olaylar — denetimin konusu bunlar.

    BİREBİR olay_denetim.py:99 / olay_tara.py:109 / olay_denetim2.py:209 süzgeci.
    RETRO DIŞARIDA: retro kayıtları biz ürettik (sera.retro), canlı sistemin kararı değil.
    """
    return [e for e in _ev_listesi(olaylar) if e.get("kind") == "person" and not e.get("retro")]


def olay_ts(e):
    """Olayın TESPİT zamanı: det_ts varsa o, yoksa ts. BİREBİR olay_denetim2.py:215."""
    return int(e.get("det_ts") or e.get("ts") or 0)


# ==========================================================================
#  KANIT KARELERİ  (pre-roll + çizim tuzakları burada kapanır)
# ==========================================================================
def kanit_kareleri(eid, arsiv_=None):
    """Olayın TEMİZ kanıt kareleri. BİREBİR olay_tara2.py:kanit_kareleri.

    Her numaralı kare için:
      · `<n>_raw.jpg` varsa (25 Tem sonrası)  → HAM kare kullanılır (kaynak="ham")
      · yoksa `<n>.jpg` inpaint'lenir         → kaynak="temizlenmis"
      · çizilen dikdörtgen ayrıca döner       → canlı sistemin kutusu (bedava etiket)
    `hd.jpg` TEMİZDİR ama olaydan ~50 sn SONRA çekilir → rol="gec", KARARA GİRMEZ.

    -> [(ad, img, canli_kutu, kaynak, rol)]
    """
    d = arsiv.olay_dizin(eid, arsiv_)
    if not os.path.isdir(d):
        return []
    fs = [os.path.basename(x) for x in glob.glob(os.path.join(d, "*.jpg"))]
    idx = sorted({m.group(1) for m in (re.match(r"^(\d+)(_raw)?\.jpg$", f) for f in fs) if m})
    out = []
    for i in idx:
        rp = os.path.join(d, "%s_raw.jpg" % i)
        cp = os.path.join(d, "%s.jpg" % i)
        cizili = cv2.imread(cp) if os.path.exists(cp) else None
        canli = cizim_kutusu(cizili, yontem="projeksiyon") if cizili is not None else None
        if os.path.exists(rp):
            img = cv2.imread(rp)
            kaynak = "ham"
        elif cizili is not None:
            img = cizim_temizle(cizili, canli)
            kaynak = "temizlenmis"
        else:
            continue
        if img is not None:
            out.append(("%s.jpg" % i, img, canli, kaynak, "an"))
    hp = os.path.join(d, "hd.jpg")
    if os.path.exists(hp):
        img = cv2.imread(hp)
        if img is not None:
            out.append(("hd.jpg", img, None, "hd", "gec"))
    return out


class Motor:
    """Dedektör + doğrulayıcı ikilisi. olay_denetim2.py:Motor'un sera paketi karşılığı.

    Fark yok, sadece sahibi değişti: kutu üretimi sera.dedektor'a, gömü+kafa
    sera.dogrulayici'ya devredildi. İki davranış BİLEREK korundu:
      · kutular(): NMS YOK, kutu kare sınırına KIRPILMAZ (Motor.kutular böyleydi)
      · skor():    kırpma tutmazsa 0.0 (Motor.dog böyleydi; sera.dogrulayici None döner)
    """

    def __init__(self, kafa=None, iplik=None, v3=True):
        from . import dedektor as _dedektor
        from . import dogrulayici as _dogrulayici
        n = int(iplik or IPLIK_DENETIM)
        self.det = _dedektor.Dedektor(threads=n)
        self.dog = _dogrulayici.Dogrulayici(kafa_json=kafa or ayar.kafa_yolu(v3=v3), threads=n)
        k = self.dog.kafa or {}
        print("dogrulayici kafa: %s | surum %s"
              % (os.path.basename(self.dog.kafa_json), (k.get("egitim") or {}).get("surum")),
              flush=True)

    def kutular(self, img, esik=DET_ESIK, min_alan=MIN_ALAN):
        """BİREBİR olay_denetim2.py:Motor.kutular — sinirla=False, nms=None."""
        return self.det.kutular(img, esik=esik, min_alan=min_alan, nms=None, sinirla=False)

    def skor(self, img, kutu):
        """BİREBİR olay_denetim2.py:Motor.dog — kırpma tutmazsa 0.0 (None değil)."""
        s = self.dog.skor(img, kutu)
        return 0.0 if s is None else float(s)


def olay_skorla(eid, motor=None, arsiv_=None):
    """Olayın TÜM karelerinin EN İYİ doğrulayıcı skoru + o karenin kutusu.

    BİREBİR olay_denetim2.py:olay_skorla. Akış:
      1. ham (_raw) kareler önce, sonra çiziliyler (arsiv.olay_kareleri_ciftler)
      2. çizili karede canlı kutu geri kazanılır + çizgi inpaint'lenir
      3. dedektörün ilk 3 kutusu + (varsa) canlı çizim kutusu aday olur
      4. adayların EN YÜKSEK doğrulayıcı skoru olayın skorudur   ← PRE-ROLL TUZAĞI BURADA KAPANIR

    -> {"dog","det","kare","kutu","n_kare","cizim_kurtarma","ham_var"} | None
    """
    M = motor or Motor()
    kareler = arsiv.olay_kareleri_ciftler(eid, arsiv_)
    if not kareler:
        return None
    en = {"dog": -1.0, "det": 0.0, "kare": None, "kutu": None, "n_kare": len(kareler),
          "cizim_kurtarma": False, "ham_var": any(h for _, h in kareler)}
    for p, ham in kareler:
        img = cv2.imread(p)
        if img is None:
            continue
        kkutu = None
        if not ham:
            kkutu = cizim_kutusu(img, yontem="bilesen")     # canlı sistemin gördüğü kutu
            if kkutu is not None:
                img = cizim_temizle(img, kkutu)             # çizgiyi inpaint ile sil
        kutular = M.kutular(img)
        adaylar = [k["kutu"] for k in kutular[:TOP_K]]
        if kkutu is not None:
            adaylar.append(list(kkutu))                     # dedektör bulamazsa canlı kutu
        for i, kutu in enumerate(adaylar):
            d = M.skor(img, kutu)
            if d > en["dog"]:
                en.update({"dog": d, "kare": p, "kutu": [round(float(v), 1) for v in kutu],
                           "det": kutular[i]["skor"] if i < len(kutular) else -1.0,
                           "cizim_kurtarma": bool(kkutu is not None and i >= len(kutular))})
    return en if en["dog"] >= 0 else None


# ==========================================================================
#  EŞİK KALİBRASYONU  (kafadan eşik YOK)
# ==========================================================================
def kalibre(motor=None, yaz=True):
    """Karar eşiğini BAĞIMSIZ TP/FP denetim etiketleriyle seç. BİREBİR olay_denetim2.py:kalibre.

    Kaynak: gate/labels.json — 119 kayıtlık DOĞRULAYICI DENETİM dosyası (TP/FP/BELIRSIZ).
    ⚠ Bu dosya EĞİTİM ETİKETİ DEĞİLDİR (eğitim seti 946'lık labels_946.json).

    yanlis_esik = max(0.02, min(TP) * 0.9)   → TP'lerin hiçbirini kesmemesi hedeflenir
    gercek_esik = quantile(FP, 0.98)         → FP'lerin en fazla %2'si geçer

    ⚠ TEST ÖLÜ KONTROLÜ: eşik hiçbir FP yakalamıyorsa denetim bir şey üretemez; uyarır.
    -> dict | None  (yeterli TP/FP yoksa None — "kalibre edilemedi" der, uydurmaz)
    """
    M = motor or Motor()
    try:
        with open(ayar.DENETIM) as f:
            lab = json.load(f)
        q = arsiv.kuyruk()
    except Exception as e:
        if yaz:
            print("kalibrasyon atlandi:", str(e)[:80], flush=True)
        return None
    tp, fp = [], []
    for fid, v in lab.items():
        et = v if isinstance(v, str) else v.get("v")
        it = q.get(fid)
        if not it or et not in ("TP", "FP"):
            continue
        box = it.get("pbox") or it.get("kutu")
        p = arsiv.vps2yerel(it.get("p") or "")
        if not box or not os.path.exists(p):
            continue
        img = cv2.imread(p)
        if img is None:
            continue
        (tp if et == "TP" else fp).append(M.skor(img, box))
    if len(tp) < 20 or len(fp) < 20:
        if yaz:
            print("kalibrasyon icin yeterli TP/FP yok:", len(tp), len(fp), flush=True)
        return None
    tp, fp = np.array(tp), np.array(fp)
    yanlis_esik = float(max(0.02, np.min(tp) * 0.9))
    gercek_esik = float(np.quantile(fp, 0.98))
    kal = {"n_TP": int(len(tp)), "n_FP": int(len(fp)),
           "TP_min": float(tp.min()), "TP_medyan": float(np.median(tp)),
           "FP_medyan": float(np.median(fp)), "FP_q98": float(np.quantile(fp, 0.98)),
           "yanlis_esik": yanlis_esik, "gercek_esik": gercek_esik,
           "kesilen_TP": int((tp < yanlis_esik).sum()),
           "yakalanan_FP": int((fp < yanlis_esik).sum())}
    if yaz:
        print("KALIBRASYON: TP n=%d medyan %.3f min %.3f | FP n=%d medyan %.3f q98 %.3f"
              % (len(tp), np.median(tp), tp.min(), len(fp), np.median(fp),
                 np.quantile(fp, 0.98)), flush=True)
        print("  yanlis_esik %.3f -> kesilen TP %d/%d, yakalanan FP %d/%d"
              % (yanlis_esik, kal["kesilen_TP"], len(tp), kal["yakalanan_FP"], len(fp)),
              flush=True)
        if kal["yakalanan_FP"] == 0:
            print("  ⚠ TEST OLU: bu esik hicbir FP yakalamiyor, denetim bir sey uretemez.",
                  flush=True)
    return kal


# ==========================================================================
#  DENETİM
# ==========================================================================
def _kayitli_denetim(kaynak=None):
    """Diskteki denetim çıktısını oku. -> (yol, veri) | (None, None)"""
    adaylar = [kaynak] if kaynak else list(KAYNAK_ONCELIK)
    for p in adaylar:
        if p and os.path.exists(p):
            with open(p) as f:
                return p, json.load(f)
    return None, None


def denetle(olaylar=None, kaynak=None, yeniden=False, motor=None, yaz=None, sessiz=False):
    """Canlı person olaylarını yanlis / gercek / belirsiz / kare_yok kovalarına ayır.

    VARSAYILAN: DİSKTEKİ DENETİMİ OKUR, YENİDEN ÖLÇMEZ. (Bu turda başka bir ajan
    gate/olay_karar.json + gate/olay_denetim.json üretti; 178 olayı yeniden taramak
    ~40 dk CPU ve aynı sayıyı verir.) Hangi dosyanın okunduğu `_kaynak`ta raporlanır.

    kaynak   : belirli bir denetim JSON'u; None → KAYNAK_ONCELIK sırası
               (olay_karar.json → olay_denetim.json → olay_denetim2.json)
    yeniden  : True ise DİSKİ YOK SAY, olay_denetim2.py protokolüyle yeniden ölç
    yaz      : yeniden ölçümün yazılacağı JSON yolu (None → yazma)

    -> {"yanlis": [...], "gercek": [...], "belirsiz": [...], "kare_yok": [...],
        "_kaynak": <yol|"olculdu">, "esik": {...}}
    """
    if not yeniden:
        p, d = _kayitli_denetim(kaynak)
        if d is not None:
            kov = {k: list(d.get(k, [])) for k in KOVALAR}
            kov["_kaynak"] = p
            kov["esik"] = d.get("esik", {})
            if not sessiz:
                print("kayitli denetim okundu: %s  (%s)"
                      % (p, " · ".join("%s %d" % (k, len(kov[k])) for k in KOVALAR)), flush=True)
                print("  esik: %s" % json.dumps(kov["esik"], ensure_ascii=False), flush=True)
            return kov
        if not sessiz:
            print("kayitli denetim YOK -> yeniden olculuyor", flush=True)

    M = motor or Motor()
    kal = kalibre(M, yaz=not sessiz)
    # ⚠ KALİBRASYON YOKSA 0.10 GİBİ BİR SAYI UYDURMA: fold-dışı OOF eşiğine düş.
    #   olay_karar.py'nin varlık sebebi tam buydu — olay_denetim2.py kalibrasyon boş
    #   çıkınca 0.10 kullanmış, o eşik gerçek insanların %5'ini siliyordu (OOF q05 0.2637).
    yanlis_esik = (kal or {}).get("yanlis_esik") or ayar.yanlis_esik()
    gercek_esik = (kal or {}).get("gercek_esik") or ayar.DOG_ESIK
    if not sessiz:
        print("karar esikleri: yanlis < %.6f · gercek >= %.2f  (kaynak: %s)"
              % (yanlis_esik, gercek_esik, "kalibre" if kal else "oof_esik.json"), flush=True)

    ev = person_olaylari(olaylar if olaylar is not None else olaylari_cek())
    if not sessiz:
        print("denetlenecek canli person olayi: %d" % len(ev), flush=True)

    kova = {k: [] for k in KOVALAR}
    for i, e in enumerate(ev):
        r = olay_skorla(e.get("id"), M)
        ts = olay_ts(e)
        kayit = {"id": e.get("id"), "ts": ts, "cam": e.get("cam"),
                 "gun": arsiv.yerel_zaman(ts, "%Y-%m-%d"),
                 "saat": arsiv.yerel_zaman(ts, "%H:%M:%S"),
                 "suspect": bool(e.get("suspect")), "why": e.get("why")}
        if r is None:
            kayit["sebep"] = "olay klasorunde kanit karesi yok"
            kova["kare_yok"].append(kayit)
        else:
            kayit.update({"dog": round(r["dog"], 4), "det": round(r["det"], 4),
                          "n_kare": r["n_kare"], "kutu": r["kutu"],
                          "kare": (r["kare"] or "").replace(ARSIV + "/", ""),
                          "cizim_kurtarma": r["cizim_kurtarma"]})
            if r["dog"] < yanlis_esik:
                kayit["sebep"] = "dogrulayici %.4f < %.4f" % (r["dog"], yanlis_esik)
                kova["yanlis"].append(kayit)
            elif r["dog"] >= gercek_esik:
                kova["gercek"].append(kayit)
            else:
                kayit["sebep"] = "%.4f <= %.4f < %.2f" % (yanlis_esik, r["dog"], gercek_esik)
                kova["belirsiz"].append(kayit)
        if not sessiz and (i + 1) % 25 == 0:
            print("  %d/%d  (yanlis %d · gercek %d · belirsiz %d · karesiz %d)"
                  % (i + 1, len(ev), len(kova["yanlis"]), len(kova["gercek"]),
                     len(kova["belirsiz"]), len(kova["kare_yok"])), flush=True)

    kova["_kaynak"] = "olculdu"
    kova["esik"] = {"yanlis": yanlis_esik, "gercek": gercek_esik,
                    "kaynak": "kalibre" if kal else "oof_esik.json"}
    if yaz:
        with open(yaz, "w") as f:
            json.dump({**{k: kova[k] for k in KOVALAR}, "esik": kova["esik"],
                       "kalibrasyon": kal, "kafa": os.path.basename(M.dog.kafa_json),
                       "uretim": "sera.olay.denetle(yeniden=True)"},
                      f, indent=1, default=float, ensure_ascii=False)
        if not sessiz:
            print("YAZILDI", yaz, flush=True)
    return kova


def kapi_bulgusu(karar=None, yaz=True):
    """ŞÜPHELİ KAPISININ MALİYETİ — bildirim ATILMAYAN olayların gerçek durumu.

    BİREBİR olay_karar.py'nin `supheli_kapisi` bölümü. Sistem "şüpheli" deyip telefonu
    öttürmediği olayların kaçı gerçekten insandı? Bu, ikinci kapının KAÇIRMA maliyetidir
    ve bu modülün başındaki BULGU'nun sayısal dayanağıdır.

    -> {"kapi": {ad: {yanlis,gercek,belirsiz}}, "bastirilmis_gercek": n,
        "bildirilmis_yanlis": n, "kurtarilabilir": n, "_kaynak": yol}
    """
    p, d = _kayitli_denetim(karar or KARAR_JSON)
    if d is None:
        raise RuntimeError("karar dosyasi yok: %s" % (karar or KARAR_JSON))
    why = collections.defaultdict(collections.Counter)
    for k in ("yanlis", "gercek", "belirsiz"):
        for x in d.get(k, []):
            if x.get("suspect"):
                why[x.get("why") or "?"][k] += 1
    kapi = {w: dict(c) for w, c in why.items()}
    bastirilmis = sum(c.get("gercek", 0) for c in kapi.values())
    kurtarilabilir = sum(c.get("gercek", 0) for w, c in kapi.items() if w in VER_KURTAR)
    bildirilmis_yanlis = sum(1 for x in d.get("yanlis", []) if not x.get("suspect"))
    r = {"kapi": kapi, "bastirilmis_gercek": bastirilmis,
         "kurtarilabilir": kurtarilabilir, "bildirilmis_yanlis": bildirilmis_yanlis,
         "ver_kurtar": list(VER_KURTAR), "ver_kurtar_esik": VER_KURTAR_ESIK, "_kaynak": p}
    if yaz:
        print("ŞÜPHELİ KAPISI — bildirim ATILMAYAN olayların gerçek durumu (%s)"
              % os.path.basename(p))
        for w, c in sorted(kapi.items(), key=lambda kv: -sum(kv[1].values())):
            print("   %-14s n=%-3d  GERCEK %-2d · yanlis %-2d · belirsiz %d%s"
                  % (w, sum(c.values()), c.get("gercek", 0), c.get("yanlis", 0),
                     c.get("belirsiz", 0), "   <- VER_KURTAR" if w in VER_KURTAR else ""))
        print("   bastirilmis GERCEK insan       : %d  (telefon otmedi)" % bastirilmis)
        print("   VER_KURTAR ile kurtarilabilir  : %d  (esik %.2f)" % (kurtarilabilir,
                                                                       VER_KURTAR_ESIK))
        print("   bildirim GITMIS ama YANLIS     : %d  (aile bosuna telaslanmis)"
              % bildirilmis_yanlis)
        print("   ⚠ person_watch_v3.py:1049 yorumu 14 diyor; bu tablo %d diyor — ikisi de"
              % kurtarilabilir)
        print("     kayitta, havuz/esik farki cozulmedi. Kafadan tek sayi secilmedi.")
    return r


# ==========================================================================
#  LOEO / LOCO DENETİMİ  (olay_denetim.py çekirdeği — önbellekli gömüler üzerinde)
# ==========================================================================
def _egitim_seti_763():
    """763 kare etiketinden 'cok HARIC' varyantı. BİREBİR olay_denetim.py:egitim_seti.

    ⚠ 763'LÜK SET BİLEREK: olay_denetim.py'nin sayıları bununla üretildi. Yeni 946'lık
      setle çalışmak isteyen sera.etiket.birlestir_kayitlar()'ı kullanır — ama o zaman
      kayıtlı olay_denetim.json ile kıyas TEK DEĞİŞKENLİ olmaz.
    """
    z = np.load(ayar.GOMU_763, allow_pickle=True)
    F, fid = z["F"], list(z["fid"])
    with open(ayar.ETIKET_763) as f:
        lab = json.load(f)
    q = arsiv.kuyruk(ayar.KUYRUK_763)
    try:
        with open(ayar.ETIKET_DENETIM) as f:
            sup = {x["fid"] for x in json.load(f)["suphe"]}
    except Exception:
        sup = set()
    X, y, eids, cams = [], [], [], []
    for i, f_ in enumerate(fid):
        if f_ in sup:
            continue
        v = lab.get(f_, {}).get("v")
        if v not in ("var", "yok"):
            continue
        it = q.get(f_, {})
        m = re.search(r"/events/([^/]+)/", it.get("p", ""))
        X.append(F[i])
        y.append(1 if v == "var" else 0)
        eids.append(m.group(1) if m else None)
        cams.append(it.get("cam"))
    return (np.array(X, np.float32), np.array(y),
            np.array(eids, object), np.array(cams, object))


_RE_TL = re.compile(r"/(20\d{6})/(\d{4})\.jpg$")


def _ts_timeline(p):
    """BİREBİR olay_denetim.py:ts_timeline — SADECE timeline/<gun>/<HHMM>.jpg şeması.
    Başka şemada None döner ve çağıran kaydı eler; bu eleme davranışı sayıların parçası."""
    from datetime import datetime
    m = _RE_TL.search(p or "")
    if not m:
        return None
    g, s = m.group(1), m.group(2)
    return int(datetime(int(g[:4]), int(g[4:6]), int(g[6:8]),
                        int(s[:2]), int(s[2:]), tzinfo=arsiv.TZ).timestamp() * 1000)


def _kafa_egit(X, y):
    """StandardScaler + LogisticRegression(C=0.05). BİREBİR olay_denetim.py:kafa."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(X)
    clf = LogisticRegression(C=ayar.C_LOJ, max_iter=ayar.MAX_ITER,
                             class_weight=ayar.SINIF_AGIRLIK)
    clf.fit(sc.transform(X), y)
    return sc, clf


def _kafa_skorla(kf, X):
    sc, clf = kf
    return clf.predict_proba(sc.transform(X))[:, 1]


def loeo_denetim(olaylar=None, yaz=None, sessiz=False):
    """OLAY-DIŞLA (LOEO) + KAMERA-DIŞLA (LOCO) denetim. olay_denetim.py'nin çekirdeği.

    ÖLÇÜM TAUTOLOJİSİ SAVUNMASI (bu fonksiyonun varlık sebebi): canlı doğrulayıcı 763 kare
    etiketiyle eğitildi ve o etiketlerin 186'sı TAM DA bu olayların klasörlerinden geliyor.
    "Canlı skorla olayları denetle" demek modeli kendi eğitim örneğinde sınamaktır. Bu yüzden
    her olay, o olayın karelerini HİÇ GÖRMEMİŞ bir kafayla (LOEO) skorlanır; ek olarak aynı
    kameradaki sabit yanlış nesneler eğitimden tamamen çıkarılarak (LOCO) da skorlanır.

    ⚠ YENİDEN TARAMA YOK: gömüler gate/olay_gomu2.npz + olay_meta2.json'dan okunur
      (olay_tara2.py bir kez üretti). Sadece kafa yeniden eğitilir — saniyeler sürer.

    ⚠ EŞİK YUVARLANMAZ: T_yanlis en düşük TP skorunun TA KENDİSİDİR; 4 haneye yuvarlamak
      eşiği o TP'nin ÜSTÜNE çıkarıp gerçek insanı "yanlış" kovasına atıyordu.

    ⚠ EŞİK KOŞUDAN KOŞUYA ~1e-6 OYNAR (2 Ağu'da ölçüldü, refactor'un suçu DEĞİL):
      gate/olay_denetim.json'daki T_yanlis 0.015071708709001541 iken, ESKİ olay_denetim.py
      aynı veriyle tekrar koşturulduğunda 0.015071690655875854 verdi — bu modül de tam
      olarak o ikinci değeri verdi (17 hane birebir). Kaynak: sklearn lbfgs/BLAS'ın koşu
      içi belirsizliği. Kovalar ve id kümeleri her üç koşuda da AYNI; eşiği tam sayı olarak
      kıyaslayan bir test yazacaksan bunu bil, "logic bozuldu" diye okuma.

    -> {"yanlis","gercek","belirsiz","kare_yok","kalibrasyon","ic_dogrulama","esik_egrisi",
        "silinebilir","esik","ozet"}
    """
    for p in (OLAY_GOMU2, OLAY_META2, ayar.GOMU_763, ayar.DENETIM):
        if not os.path.exists(p):
            raise RuntimeError("gerekli dosya yok: %s" % p)

    with open(OLAY_META2) as f:
        meta = json.load(f)["meta"]
    Fev = np.load(OLAY_GOMU2)["F"]
    with open(ayar.DENETIM) as f:
        GT = json.load(f)
    ev = person_olaylari(olaylar if olaylar is not None else olaylari_cek())

    X, y, tr_eid, tr_cam = _egitim_seti_763()
    if not sessiz:
        print("egitim karesi: %d (poz %d / neg %d) | olaydan gelen: %d"
              % (len(y), y.sum(), len(y) - y.sum(), sum(1 for e in tr_eid if e)), flush=True)

    tam = _kafa_egit(X, y)                    # tüm veri = canlı kafanın eşdeğeri (TOTOLOJİK)
    loco = {}
    for c in sorted({int(c) for c in tr_cam if c is not None}):
        m = np.array([(cc is None or int(cc) != c) for cc in tr_cam])
        if len(set(y[m])) == 2:
            loco[c] = _kafa_egit(X[m], y[m])
    if not sessiz:
        print("kamera-disla kafa: %s" % sorted(loco), flush=True)

    # rol="an": tespit anındaki kanıt kareleri → KARARA GİRER
    # rol="gec": hd.jpg, olaydan ~50 sn SONRA → sadece destekleyici bilgi
    per_ev = collections.defaultdict(list)
    per_hd = collections.defaultdict(list)
    kare_sayaci = collections.defaultdict(set)
    for r in meta:
        kare_sayaci[r["eid"]].add(r["kare"])
        if r.get("gi", -1) >= 0:
            (per_hd if r.get("rol") == "gec" else per_ev)[r["eid"]].append(
                (r["gi"], r.get("det"), r["kare"], r["box"],
                 r.get("kutu_kaynak"), r.get("kaynak")))

    loeo_cache, sonuc = {}, {}
    for i, e in enumerate(ev):
        eid = e["id"]
        cand = per_ev.get(eid, [])
        cam = e.get("cam")
        nk = len(kare_sayaci.get(eid, ()))
        m = tr_eid != eid                      # LOEO: bu olayın kareleri eğitimden çıkar
        if m.all():
            kf = tam
        else:
            if eid not in loeo_cache:
                loeo_cache[eid] = _kafa_egit(X[m], y[m])
            kf = loeo_cache[eid]
        hd_c = per_hd.get(eid, [])
        dog_hd = (float(np.max(_kafa_skorla(kf, Fev[np.array([c[0] for c in hd_c])])))
                  if hd_c else None)
        if not cand:
            sonuc[eid] = {"dog": None, "det": 0.0, "kare": None, "box": None,
                          "dog_loco": None, "dog_tam": None, "dog_hd": dog_hd,
                          "n_kutu": 0, "n_kare": nk, "kutu_kaynak": None, "goruntu": None}
            continue
        Xe = Fev[np.array([c[0] for c in cand])]
        pl = _kafa_skorla(kf, Xe)
        pt = _kafa_skorla(tam, Xe)
        pc = _kafa_skorla(loco[int(cam)], Xe) if (cam and int(cam) in loco) else pl
        j = int(np.argmax(pl))
        sonuc[eid] = {"dog": float(pl[j]), "det": float(cand[j][1] or 0.0), "kare": cand[j][2],
                      "box": cand[j][3], "kutu_kaynak": cand[j][4], "goruntu": cand[j][5],
                      "dog_loco": float(np.max(pc)), "dog_tam": float(np.max(pt)),
                      "dog_hd": dog_hd, "n_kutu": len(cand), "n_kare": nk}
        if not sessiz and (i + 1) % 40 == 0:
            print("  olay %d/%d skorlandi" % (i + 1, len(ev)), flush=True)

    # ------------------------------------------------ KALİBRASYON (119 etiketli olay)
    kal = [(eid, GT[eid]["v"], sonuc[eid]) for eid in GT if eid in sonuc]
    kal = [(a, b, c) for a, b, c in kal if b in ("TP", "FP")]
    tp = [c for a, b, c in kal if b == "TP"]
    fp = [c for a, b, c in kal if b == "FP"]

    def sk(r, alan="dog"):
        return -1.0 if r[alan] is None else r[alan]

    # KUTUSUZ olaylar: dedektör 0.05'te bile kutu bulamıyor. Etiketli TP'lerden biri
    # kutusuzsa "kutu yok = yanlış" kuralı GERÇEK insanı keser — o yüzden ayrı raporlanır.
    kutusuz = {"TP": [a for a, b, c in kal if b == "TP" and c["dog"] is None],
               "FP": [a for a, b, c in kal if b == "FP" and c["dog"] is None]}

    rapor = {}
    for alan, ad in (("dog", "LOEO (olay-disla)"), ("dog_loco", "LOCO (kamera-disla)"),
                     ("dog_tam", "TAM veri (= canli, TOTOLOJIK)")):
        tps = sorted(sk(r, alan) for r in tp if r[alan] is not None)
        fps = sorted(sk(r, alan) for r in fp if r[alan] is not None)
        t_yanlis = tps[0]
        t_gercek = (fps[-1] if fps else 0.0)
        yakalanan = sum(1 for v in fps if v < t_yanlis)
        gecen = sum(1 for v in tps if v > t_gercek)
        rapor[alan] = {"ad": ad, "T_yanlis": float(t_yanlis), "T_gercek": float(t_gercek),
                       "T_yanlis_goster": round(float(t_yanlis), 4),
                       "kacirma0_yakalanan_FP": int(yakalanan), "n_FP": len(fps),
                       "yanlis0_gecen_TP": int(gecen), "n_TP": len(tps),
                       "kutusuz_TP": len(kutusuz["TP"]), "kutusuz_FP": len(kutusuz["FP"]),
                       "auc": None}
        try:
            from sklearn.metrics import roc_auc_score
            yy = [1] * len(tps) + [0] * len(fps)
            rapor[alan]["auc"] = round(float(roc_auc_score(yy, tps + fps)), 4)
        except Exception:
            pass
        if not sessiz:
            print("%-34s T_yanlis=%.3f -> %d/%d FP yakalanir (0 TP kesilir) | "
                  "T_gercek=%.3f -> %d/%d TP gecer | AUC %s"
                  % (ad, t_yanlis, yakalanan, len(fps), t_gercek, gecen, len(tps),
                     rapor[alan]["auc"]), flush=True)

    # eşik SEÇİMİ de fold-dışı olsun: 5 katlı olay-gruplu iç doğrulama
    import random
    rnd = random.Random(7)
    idx = list(range(len(kal)))
    rnd.shuffle(idx)
    kat = [idx[i::5] for i in range(5)]
    kes_top = yak_top = ntp_top = nfp_top = 0
    esikler = []
    for f_ in range(5):
        te = set(kat[f_])
        tr = [i for i in idx if i not in te]
        t_tr = min(sk(kal[i][2]) for i in tr
                   if kal[i][1] == "TP" and kal[i][2]["dog"] is not None)
        esikler.append(round(float(t_tr), 4))
        for i in te:
            if kal[i][2]["dog"] is None:
                continue
            v = sk(kal[i][2])
            if kal[i][1] == "TP":
                ntp_top += 1
                kes_top += (v < t_tr)
            else:
                nfp_top += 1
                yak_top += (v < t_tr)
    ic = {"esikler": esikler, "kesilen_TP": int(kes_top), "n_TP": ntp_top,
          "yakalanan_FP": int(yak_top), "n_FP": nfp_top}

    # EŞLEŞTİRİLMİŞ ÇALIŞMA NOKTASI EĞRİSİ: kaçırma sabitlenmeden önce fiyat listesi
    tps_ = [sk(c) for a, b, c in kal if b == "TP" and c["dog"] is not None]
    fps_ = [sk(c) for a, b, c in kal if b == "FP" and c["dog"] is not None]
    egri = [{"T": T, "kesilen_TP": sum(1 for v in tps_ if v < T), "n_TP": len(tps_),
             "yakalanan_FP": sum(1 for v in fps_ if v < T), "n_FP": len(fps_)}
            for T in (0.015, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)]

    T_Y = rapor["dog"]["T_yanlis"]
    T_G = rapor["dog"]["T_gercek"]

    # timeline desteği (bağımsız kanal): aynı kamerada ±8 dk içinde doğrulayıcı >= 0.5 kare
    # ⚠ BİLEREK arsiv.ts_of DEĞİL: ts_of hasat/diag/olay adlandırmalarını da çözer (üst küme).
    #   olay_denetim.py:ts_timeline SADECE timeline şemasını tanıyor, diğerlerinde None dönüp
    #   kaydı ELİYORDU. ts_of'a geçmek destek havuzunu büyütür ve `kesin` bayrağını kaydırır —
    #   yani sayıları değiştirir. Refactor mantığı korur: strict timeline parser kullanılıyor.
    tl = collections.defaultdict(list)
    if os.path.exists(HACIM_KURU):
        with open(HACIM_KURU) as f:
            for r in json.load(f)["kayit"]:
                t = _ts_timeline(r["p"])
                if t and r.get("cam"):
                    tl[int(r["cam"])].append((t, float(r["dog"]), float(r["det"])))
        for k in tl:
            tl[k].sort()

    def timeline_destek(cam, ts, pencere_dk=8):
        if not cam:
            return None
        en = None
        for t, dg, _dt in tl.get(int(cam), []):
            if abs(t - ts) <= pencere_dk * 60000:
                en = dg if en is None else max(en, dg)
        return None if en is None else round(en, 3)

    kova = {k: [] for k in KOVALAR}
    for e in ev:
        eid = e["id"]
        r = sonuc[eid]
        kayit = {"id": eid, "ts": e["ts"], "cam": e.get("cam"),
                 "gun": arsiv.yerel_zaman(e["ts"], "%Y-%m-%d"),
                 "saat": arsiv.yerel_zaman(e["ts"], "%H:%M:%S"),
                 "dog": None if r["dog"] is None else round(r["dog"], 4),
                 "dog_loco": None if r["dog_loco"] is None else round(r["dog_loco"], 4),
                 "dog_canli": None if r["dog_tam"] is None else round(r["dog_tam"], 4),
                 "dog_hd": None if r.get("dog_hd") is None else round(r["dog_hd"], 4),
                 "det": round(r["det"], 4), "n_kare": r["n_kare"], "n_kutu": r["n_kutu"],
                 "kare": r.get("kare"), "box": r.get("box"),
                 "kutu_kaynak": r.get("kutu_kaynak"), "goruntu": r.get("goruntu"),
                 "suspect": bool(e.get("suspect")), "why": e.get("why"),
                 "gt": GT.get(eid, {}).get("v"), "gt_ne": GT.get(eid, {}).get("what"),
                 "tl_destek": timeline_destek(e.get("cam"), e["ts"])}
        kayit["kesin"] = bool(
            r["n_kare"] > 0 and
            (r["dog"] is None or r["dog"] < T_Y) and
            (r["dog_loco"] is None or r["dog_loco"] < T_Y) and
            (kayit["tl_destek"] is None or kayit["tl_destek"] < 0.50))
        if r["n_kare"] == 0:
            kayit["sebep"] = "olay klasoru bos — kanit karesi yazilamamis"
            kova["kare_yok"].append(kayit)
        elif r["dog"] is None:
            kayit["sebep"] = ("kanit karesinde hicbir aday kutu yok "
                              "(det<0.05 ve cizim kutusu bulunamadi)")
            kova["belirsiz"].append(kayit)
        elif r["dog"] < T_Y:
            kayit["sebep"] = "dogrulayici(olay-disla) %.3f < T_yanlis %.3f" % (r["dog"], T_Y)
            kova["yanlis"].append(kayit)
        elif r["dog"] > T_G:                  # sınırdaki FP'nin KENDİSİ dışarıda kalsın
            kayit["sebep"] = "dogrulayici(olay-disla) %.3f > T_gercek %.3f" % (r["dog"], T_G)
            kova["gercek"].append(kayit)
        else:
            kayit["sebep"] = "T_yanlis(%.3f) <= %.3f < T_gercek(%.3f)" % (T_Y, r["dog"], T_G)
            kova["belirsiz"].append(kayit)
    for k in kova:
        kova[k].sort(key=lambda r: r["ts"])

    why_isabet = {}
    for k, lst in kova.items():
        for r in lst:
            if not r["suspect"]:
                continue
            w = r["why"] or "?"
            d = why_isabet.setdefault(w, {"n": 0, "yanlis": 0, "gercek": 0,
                                          "belirsiz": 0, "kare_yok": 0})
            d["n"] += 1
            d[k] += 1
    for w, d in why_isabet.items():
        karar = d["yanlis"] + d["gercek"]
        d["isabet"] = round(d["yanlis"] / karar, 3) if karar else None

    # SİLİNEBİLİR: iki kanıt kaynağı birleşir — insan etiketi (gt=FP) · model (LOEO < T_yanlis)
    silinebilir = []
    for k in KOVALAR:
        for r in kova[k]:
            if r["gt"] == "FP":
                silinebilir.append(dict(r, kanit="insan-etiketi", kova=k))
            elif r["gt"] is None and k == "yanlis":
                silinebilir.append(dict(r, kanit="model", kova=k))
    silinebilir.sort(key=lambda r: r["ts"])

    ozet_ = {k: len(kova[k]) for k in KOVALAR}
    ozet_["silinebilir"] = len(silinebilir)
    gunler = collections.Counter(r["gun"] for r in kova["yanlis"])
    kamlar = collections.Counter(r["cam"] for r in kova["yanlis"])
    if not sessiz:
        print("\nKARAR ESIKLERI (LOEO):  yanlis < %.6f  |  belirsiz  |  gercek >= %.6f"
              % (T_Y, T_G), flush=True)
        print("KOVALAR: %s" % ozet_, flush=True)

    sonuc_d = {**kova, "why_isabet": why_isabet, "silinebilir": silinebilir,
               "esik": {"T_yanlis": T_Y, "T_gercek": T_G, "skor": "LOEO"},
               "kalibrasyon": rapor, "ic_dogrulama": ic, "esik_egrisi": egri,
               "kutusuz_GT": {"TP": kutusuz["TP"], "FP": kutusuz["FP"]},
               "ozet": ozet_, "kesin_yanlis": sum(1 for r in kova["yanlis"] if r["kesin"]),
               "yanlis_gun": dict(sorted(gunler.items())),
               "yanlis_kamera": {str(k): v for k, v in sorted(kamlar.items(),
                                                             key=lambda x: -x[1])},
               "uretim": "sera.olay.loeo_denetim (eski: olay_denetim.py faz2)",
               "not": "dog = OLAY-DISLA (LOEO) kafa; dog_canli = canli kafa (totolojik)"}
    if yaz:
        with open(yaz, "w") as f:
            json.dump(sonuc_d, f, indent=1, ensure_ascii=False, default=float)
        if not sessiz:
            print("YAZILDI", yaz, flush=True)
    return sonuc_d


# ==========================================================================
#  TEMİZLİK  (olay_temizle.py — KURU VARSAYILAN)
# ==========================================================================
def _insan_var(r):
    """Bu kaydın arkasında İNSAN etiketi var mı? BİREBİR olay_temizle.py:insan_var."""
    return r.get("gt") is not None or r.get("kanit") == "insan-etiketi"


def _dizin_boyut(p):
    t = 0
    try:
        for f in os.listdir(p):
            try:
                t += os.path.getsize(os.path.join(p, f))
            except OSError:
                pass
    except OSError:
        return None
    return t


def _hedef_coz(yanlis_idler, denetim=None):
    """Girdi ne olursa olsun {id: denetim_kaydi} üret.

    yanlis_idler:  [id, ...] · [{"id":..., "ts":..., "cam":...}, ...] · None (denetimden al)
    id listesi verilirse ts/cam KİMLİK DOĞRULAMASI için denetim dosyasından tamamlanır;
    orada da yoksa kayıt {} kalır ve doğrulama onu ATLAR (id yeniden kullanılmış olabilir).
    """
    # TÜM denetim dosyaları birleştirilir: öncelik sırasında ÖNCE gelen alan kazanır,
    # sonrakiler yalnızca EKSİK alanı doldurur. Böylece olay_karar.json'un kalibre skoru
    # korunurken olay_denetim.json'daki `gt` (insan etiketi), `dog_loco` ve `kesin` de
    # gelir — LOCO itirazı ve "insan etiketi var mı" güvenlik kontrolleri ancak bu
    # alanlar doluyken gerçekten çalışır.
    kayitli = {}
    p, d = _kayitli_denetim(denetim)
    for yol in ([denetim] if denetim else list(KAYNAK_ONCELIK)):
        if not yol or not os.path.exists(yol):
            continue
        with open(yol) as f:
            dd = json.load(f)
        for k in list(KOVALAR) + ["silinebilir"]:
            for r in dd.get(k, []):
                if not r.get("id"):
                    continue
                mevcut = kayitli.setdefault(r["id"], {})
                for alan, deger in r.items():
                    if alan not in mevcut or mevcut[alan] is None:
                        mevcut[alan] = deger
    if yanlis_idler is None:
        if d is None:
            raise RuntimeError("silinecek liste de denetim dosyasi da yok")
        return ({r["id"]: kayitli.get(r["id"], r)
                 for r in d.get("yanlis", []) if r.get("id")}, p)
    out = {}
    for x in yanlis_idler:
        if isinstance(x, dict):
            if x.get("id"):
                out[x["id"]] = dict(kayitli.get(x["id"], {}), **x)
        elif x:
            out[str(x)] = kayitli.get(str(x), {"id": str(x)})
    return out, p


def temizle(yanlis_idler=None, uygula=False, state=None, denetim=None,
            gorsel_sil=False, gorsel_dizin=None, ziyaret_koru=False,
            cap_uygula=False, haric=(), sadece=(), yaz=True):
    """Yanlış alarm olaylarını state.json'dan sil. KURU VARSAYILAN — uygula=False.

    BİREBİR olay_temizle.py:main. Güvenlik kuralları (ihlalde yazmaz, atlar):
      · SADECE verilen id listesi silinir; başka hiçbir kayda dokunulmaz.
      · RETRO KORUNUR — retro=True kayıt listede olsa bile silinmez.
      · kind != "person" olan kayıt silinmez (araç/pompa olayı listeye sızarsa yakalanır).
      · KİMLİK DOĞRULAMASI — id eşleşse bile state'teki ts/cam denetim kaydıyla tutmuyorsa
        O KAYIT ATLANIR (id yeniden kullanılmış olabilir).
      · Yazmadan ÖNCE state.json zaman damgalı yedeklenir + silinenlerin tam JSON'u ayrı
        "geri-al" dosyasına yazılır.
      · YARIŞ KORUMASI — state.json okunduktan sonra mtime/boyut değiştiyse YAZILMAZ.
      · Yazım atomik: tmp + fsync + os.replace.
      · EVENTS_CAP(4000) taşmasında kendiliğinden kırpmaz, uyarır (cap_uygula=True ile
        retro KORUNARAK en eski CANLI kayıt düşer).
      · Olay fotoğrafları varsayılan SİLİNMEZ (yaş temizleyicisi 45 günde siler).

    state=None → yerel PROVA anlık görüntüsü (SCRATCH/ev_now.json) varsa o, yoksa
    /opt/sera/state.json. ⚠ PROVA dosyasına uygula=True YAPILMAZ (anlık görüntü canlı
    state değildir; yazmak hiçbir işe yaramaz, yanılgı üretir) — açıkça reddedilir.

    -> {"silinecek": [...], "atlanan": [...], "itiraz": [...], "uygulandi": bool, ...}
    """
    hedef, den_yol = _hedef_coz(yanlis_idler, denetim)
    if sadece:
        s = set(sadece)
        hedef = {k: v for k, v in hedef.items() if k in s}
    if haric:
        h = set(haric)
        hedef = {k: v for k, v in hedef.items() if k not in h}

    state_p = state or (STATE_PROVA if os.path.exists(STATE_PROVA) else STATE_CANLI)
    prova = os.path.abspath(state_p) == os.path.abspath(STATE_PROVA)
    if uygula and prova:
        raise RuntimeError(
            "PROVA dosyasina uygula=True yapilmaz: %s bir ANLIK GORUNTU, canli state degil. "
            "Gercek silme VPS'te /opt/sera/state.json uzerinde yapilir." % state_p)
    if not os.path.exists(state_p):
        raise RuntimeError("state dosyasi yok: %s" % state_p)

    st = os.stat(state_p)
    imza0 = (st.st_mtime_ns, st.st_size)
    with open(state_p) as f:
        s = json.load(f)
    evs = s.get("events", [])
    vis = s.get("visits", [])
    imgdir = gorsel_dizin or EVIMG_DIR

    if yaz:
        print("=" * 78)
        print("OLAY TEMİZLİĞİ — %s"
              % ("UYGULA" if uygula else "KURU TUR (hiçbir şey yazılmaz)"))
        print("kaynak : %s" % (den_yol or "(elle verilen liste)"))
        print("state  : %s%s  (olay=%d · ziyaret=%d)"
              % (state_p, "  [PROVA anlık görüntü]" if prova else "", len(evs), len(vis)))
        print("=" * 78)

    byid = {}
    for i, e in enumerate(evs):
        if e.get("id"):
            byid.setdefault(e["id"], []).append(i)

    sil_idx, sil_kayit, atlanan = [], [], []
    for eid, r in hedef.items():
        yer = byid.get(eid)
        if not yer:
            atlanan.append((eid, "state'te YOK"))
            continue
        if len(yer) > 1:
            atlanan.append((eid, "state'te %d KEZ var — belirsiz, dokunulmadı" % len(yer)))
            continue
        e = evs[yer[0]]
        if e.get("retro"):
            atlanan.append((eid, "RETRO kayıt — korunuyor"))
            continue
        if e.get("kind") != "person":
            atlanan.append((eid, "kind=%s (person değil) — korunuyor" % e.get("kind")))
            continue
        if int(e.get("cam") or -1) != int(r.get("cam") or -2):
            atlanan.append((eid, "cam uyuşmuyor: state=%s denetim=%s"
                            % (e.get("cam"), r.get("cam"))))
            continue
        ts_s, ts_r = int(e.get("ts") or 0), int(r.get("ts") or 0)
        if abs(ts_s - ts_r) > 60000:
            atlanan.append((eid, "ts uyuşmuyor: %d ms fark" % abs(ts_s - ts_r)))
            continue
        sil_idx.append(yer[0])
        sil_kayit.append((r, e))

    sil_idx_set = set(sil_idx)
    sil_kayit.sort(key=lambda x: int(x[0].get("ts") or 0))

    itiraz = []
    if yaz:
        print("\nSİLİNECEK OLAYLAR (%d)" % len(sil_kayit))
        print("%-3s %-10s %-8s %-4s %-8s %-8s %-6s %-6s %-4s %s"
              % ("#", "gün", "saat", "kam", "dog", "loco", "det", "kanıt", "!", "ne"))
    for i, (r, e) in enumerate(sil_kayit, 1):
        it = (r.get("dog_loco") or 0) >= T_LOCO and not _insan_var(r)
        if it:
            itiraz.append((i, r))
        if not yaz:
            continue
        kanit = "İNSAN" if _insan_var(r) else "model"
        ne = (r.get("gt_ne") or r.get("why")
              or ("şüpheli/" + str(e.get("why")) if e.get("suspect") else "") or "-")
        print("%-3d %-10s %-8s k%-3s %-8.4f %-8.4f %-6.2f %-6s %-4s %s%s"
              % (i, r.get("gun", "?"), r.get("saat", "?"), r.get("cam"),
                 r.get("dog") or -1, r.get("dog_loco") or -1, r.get("det") or 0, kanit,
                 "LOCO" if it else "", "[KESİN] " if r.get("kesin") else "", str(ne)[:44]))

    gun = collections.Counter(r.get("gun") for r, _ in sil_kayit)
    kam = collections.Counter(r.get("cam") for r, _ in sil_kayit)
    knt = collections.Counter("insan-etiketi" if _insan_var(r) else "model-karari"
                              for r, _ in sil_kayit)
    sus = sum(1 for _, e in sil_kayit if e.get("suspect"))
    if yaz:
        print("\nGÜN     : " + " · ".join("%s=%d" % (g, n) for g, n in sorted(
            gun.items(), key=lambda x: str(x[0]))))
        print("KAMERA  : " + " · ".join("k%s=%d" % (c, n) for c, n in sorted(
            kam.items(), key=lambda x: str(x[0]))))
        print("KANIT   : " + " · ".join("%s=%d" % (k, n) for k, n in sorted(knt.items())))
        print("KESİN   : %d / %d" % (sum(1 for r, _ in sil_kayit if r.get("kesin")),
                                     len(sil_kayit)))
        print("ŞÜPHELİ : %d (bunlar zaten PUSH GÖNDERMEDİ — takvimden düşecek)" % sus)
        if itiraz:
            print("\n⚠ İKİ KAFA AYRIŞIYOR (%d) — LOEO 'yanlış' diyor ama kamera-dışı (LOCO)"
                  "\n  kafa T_LOCO=%.3f üstünde tutuyor ve insan etiketi de YOK. Silmeden"
                  "\n  önce bunlara bak; vazgeçersen: haric=[%s]"
                  % (len(itiraz), T_LOCO, ",".join(r.get("id", "?") for _, r in itiraz)))
        if atlanan:
            print("\nATLANAN (%d) — dokunulmadı:" % len(atlanan))
            for eid, sb in atlanan:
                print("   %-32s %s" % (eid, sb))

    # ---- ziyaret etkisi ----
    kalan_evs = [e for i, e in enumerate(evs) if i not in sil_idx_set]
    kalan_vid = collections.Counter(e.get("vid") for e in kalan_evs if e.get("vid"))
    dokunulan, bosalan = [], []
    silinen_id = set(e["id"] for _, e in sil_kayit)
    for v in vis:
        if not any(x in silinen_id for x in v.get("eids", [])):
            continue
        dokunulan.append(v)
        if kalan_vid.get(v.get("vid"), 0) == 0:
            bosalan.append(v)

    gorsel_ozet = None
    if gorsel_sil:
        top, yok = 0, 0
        for _, e in sil_kayit:
            b = _dizin_boyut(os.path.join(imgdir, e["id"]))
            if b is None:
                yok += 1
            else:
                top += b
        gorsel_ozet = {"klasor": len(sil_kayit) - yok, "mb": round(top / 1e6, 1), "yok": yok}

    kalan = len(evs) - len(sil_idx)
    if yaz:
        print("\nZİYARET ETKİSİ: dokunulan %d · tamamen boşalan %d%s"
              % (len(dokunulan), len(bosalan),
                 "  (ziyaret_koru=True, dokunulmayacak)" if ziyaret_koru else ""))
        if gorsel_ozet:
            print("GÖRSEL: %d klasör silinecek (%.1f MB) · %d klasör zaten yok"
                  % (gorsel_ozet["klasor"], gorsel_ozet["mb"], gorsel_ozet["yok"]))
        else:
            print("GÖRSEL: DOKUNULMUYOR (yaş temizleyicisi 45 günde siler). "
                  "gorsel_sil=True ile açılır.")
        print("\nSONUÇ  : olay %d → %d  (-%d)" % (len(evs), kalan, len(sil_idx)))
        if kalan > CAP:
            print("UYARI  : kalan olay CAP(%d) üstünde. Kendiliğinden kırpılmaz;" % CAP)
            print("         cap_uygula=True verirsen retro KORUNUR, en eski CANLI düşer.")

    rapor = {"silinecek": [dict(r, _state_kind=e.get("kind")) for r, e in sil_kayit],
             "silinecek_id": [e["id"] for _, e in sil_kayit],
             "atlanan": [{"id": a, "sebep": b} for a, b in atlanan],
             "itiraz": [r.get("id") for _, r in itiraz],
             "ziyaret_dokunulan": len(dokunulan), "ziyaret_bosalan": len(bosalan),
             "gorsel": gorsel_ozet, "state": state_p, "prova": prova,
             "olay_once": len(evs), "olay_sonra": kalan, "uygulandi": False,
             "yedek": None, "geri_al": None}

    if not uygula:
        if yaz:
            print("\nKURU TUR — hiçbir şey yazılmadı. Uygulamak için: uygula=True")
        return rapor
    if not sil_kayit:
        if yaz:
            print("\nSilinecek kayıt yok, çıkılıyor.")
        return rapor

    # ---- YAZIM ----
    st2 = os.stat(state_p)
    if (st2.st_mtime_ns, st2.st_size) != imza0:
        rapor["hata"] = "state.json okunduktan sonra DEĞİŞTİ (canlı servis yazmış) — yazılmadı"
        if yaz:
            print("\nDURDURULDU: " + rapor["hata"])
        return rapor

    dmg = int(time.time())
    yedek = "%s.temizlik-yedek-%d" % (state_p, dmg)
    shutil.copy(state_p, yedek)
    geri_al = "%s.silinen-%d.json" % (state_p, dmg)
    with open(geri_al, "w") as f:
        json.dump({"ts": dmg, "kaynak": den_yol, "events": [e for _, e in sil_kayit],
                   "visits": dokunulan}, f, ensure_ascii=False, indent=1)

    s["events"] = kalan_evs
    if not ziyaret_koru:
        yeni_vis = []
        for v in vis:
            if v not in dokunulan:
                yeni_vis.append(v)
                continue
            if kalan_vid.get(v.get("vid"), 0) == 0:
                continue                                   # olayı kalmayan ziyaret düşer
            dus = [x for x in v.get("eids", []) if x in silinen_id]
            v["eids"] = [x for x in v.get("eids", []) if x not in silinen_id]
            for eid in dus:
                e = next((ee for _, ee in sil_kayit if ee["id"] == eid), None)
                if not e:
                    continue
                if e.get("suspect"):
                    v["n_sus"] = max(0, int(v.get("n_sus") or 0) - 1)
                else:
                    v["n_ev"] = max(0, int(v.get("n_ev") or 0) - 1)
                v["n_ph"] = max(0, int(v.get("n_ph") or 0) - int(e.get("n") or 0))
            yeni_vis.append(v)
        s["visits"] = yeni_vis

    if len(s["events"]) > CAP and cap_uygula:
        s["events"].sort(key=lambda e: e.get("ts", 0))
        fazla = len(s["events"]) - CAP
        canli = [i for i, e in enumerate(s["events"]) if not e.get("retro")]
        dus = set(canli[:fazla])
        s["events"] = [e for i, e in enumerate(s["events"]) if i not in dus]
        if yaz:
            print("tavan aşıldı: %d canlı kayıt düşürüldü (retro korundu)" % fazla)

    tmp = state_p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, state_p)

    n_img = 0
    if gorsel_sil:
        for _, e in sil_kayit:
            d = os.path.join(imgdir, e["id"])
            if os.path.isdir(d) and os.path.realpath(d).startswith(
                    os.path.realpath(imgdir) + os.sep):
                shutil.rmtree(d, ignore_errors=True)
                n_img += 1

    rapor.update({"uygulandi": True, "yedek": yedek, "geri_al": geri_al,
                  "gorsel_silinen": n_img, "olay_sonra": len(s["events"])})
    if yaz:
        print("\nYAZILDI. olay: %d · ziyaret: %d · silinen: %d · görsel klasör: %d"
              % (len(s["events"]), len(s.get("visits", [])), len(sil_kayit), n_img))
        print("yedek   : %s" % yedek)
        print("geri-al : %s" % geri_al)
    return rapor


def silinecek_listesi(yol=None):
    """İKİ BAĞIMSIZ DENETİMİN ÇELİŞKİSİZ KESİŞİMİ — gate/silinecek.json.

    Bu dosya iki ayrı protokolün (LOEO ve v3-kafa/OOF) ORTAK 'yanlış' dediği olayları
    tutar; çelişki sayısı 0. temizle() için en temkinli girdi budur.
    -> ([id, ...], celiski)
    """
    p = yol or SILINECEK_JSON
    with open(p) as f:
        d = json.load(f)
    return list(d.get("silinecek", [])), list(d.get("celiski", []))


# ==========================================================================
#  ÖZET / CLI
# ==========================================================================
def ozet(yaz=True):
    """Denetim/temizlik girdilerinin varlık durumu — 'çalışıyor' demeden önce bakılacak yer."""
    d = {}
    for ad, p in (("ev_now", EV_JSON), ("karar", KARAR_JSON), ("denetim_loeo", DENETIM_JSON),
                  ("denetim_v2", DENETIM2_JSON), ("silinecek", SILINECEK_JSON),
                  ("olay_gomu2", OLAY_GOMU2), ("olay_meta2", OLAY_META2),
                  ("hacim_kuru", HACIM_KURU), ("gomu_763", ayar.GOMU_763),
                  ("gt_denetim", ayar.DENETIM), ("state_prova", STATE_PROVA)):
        d[ad] = (p, os.path.exists(p))
    if yaz:
        for ad, (p, v) in d.items():
            print("  %s %-14s %s" % ("OK  " if v else "YOK ", ad, p))
    return d


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "ozet":
        ozet()
    elif a[0] == "denetle":
        k = denetle(yeniden="--yeniden" in a)
        print(json.dumps({x: len(k[x]) for x in KOVALAR}, ensure_ascii=False))
    elif a[0] == "kapi":
        kapi_bulgusu()
    elif a[0] == "loeo":
        r = loeo_denetim()
        print(json.dumps(r["ozet"], ensure_ascii=False))
    elif a[0] == "temizle":
        ids, _ = silinecek_listesi()
        temizle(ids, uygula=False)          # KURU — uygula bilerek yok
    else:
        print(__doc__)

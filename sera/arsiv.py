# -*- coding: utf-8 -*-
"""
sera.arsiv — arşiv gezgini: kaynaklar, zaman damgası, kamera/gün, sahne grubu, olay kareleri.

DEVRALINAN (mantık BİREBİR korundu):
  kaynaklar()      ← full_scan.py:44  (sera_pipeline.py bunu zaten import ediyordu)
  kaynak_adi()     ← sera_pipeline.py:kaynak_adi
  cam_of()         ← sera_pipeline.py:cam_of (üst küme; full_scan.py/hacim_kuru.py varyantlarını kapsar)
  gun_of()         ← retro_kapsam.py:47 (üst küme; olay klasörü p-<ms>- adını da çözer)
  ts_of()          ← retro_kapsam.py:57 + retro_build.py:ts_timeline/ts_harvest (üçü birleşti)
  zaman_of()       ← sera_pipeline.py:zaman_of
  sahne()          ← oof_sweep.py:57  ⚠ SIZINTI ÖNLEYİCİ — birebir korundu
  sahne_klip()     ← train_verifier.py:42 (farklı gruplama; select_next100.py de bunu kullanır)
  gece()           ← gece_sweep.py:27  (ÖLÇÜM tanımı 20-06)
  gece_uretim()    ← vps/person_watch_v3.py:is_night (ÜRETİM tanımı 21-07)
  olay_kareleri()  ← olay_denetim2.py:kareleri_bul + person_watch_v3.py'nin PRE-ROLL kuralı
  kardes_kareler() ← retro_build.py:en_iyi_kare içindeki kardeş glob'u
  olaylastir()     ← retro_kapsam.py:olaylastir
  vps2yerel()      ← oof_sweep.py / train_verifier3.py / retro_build2.py (basit replace)
  vps2yerel_diag() ← train_verifier.py:vps2local (diag → diag_vps eşlemesi)

ARŞİV YERLEŞİMİ (2 Ağu 2026 itibarıyla ölçüldü, tahmin değil):
  timeline/kameraN/YYYYMMDD/HHMM.jpg      — zaman tüneli (5 dk'da bir kare)
  events/p-<epoch_ms>-kameraN/            — canlı olay: 1.jpg, 2.jpg, [*_raw.jpg], hd.jpg, clip.mp4
  harvest_hd/frames/[i_]k<N>_YYYYMMDD-HHMMSS[d]_NNN.jpg   — DVR hasadı kareleri
  harvest_hd/k<N>_YYYYMMDD-HHMMSS_<sure>s.h265            — kaynak klip
  diag_hd/kameraN_YYYYMMDD-HHMMSS_XX_<etiket>.jpg         — HD tanılama kareleri
  diag_vps/kameraN_YYYYMMDD-HHMMSS_NNN.jpg                — sub tanılama kareleri
"""
import os
import re
import glob
import collections
from datetime import datetime, timezone, timedelta

from . import ayar

TZ = timezone(timedelta(hours=ayar.TZ_SAAT))          # Europe/Istanbul (+03)

# --------------------------------------------------------------------- regex'ler
_RE_TIMELINE = re.compile(r"/(20\d{6})/(\d{2})(\d{2})\.jpg$")          # retro_kapsam.py:ts_of
_RE_HASAT = re.compile(r"_?k?(\d)_?(20\d{6})-(\d{6})")                 # retro_build.py:ts_harvest
_RE_OLAY = re.compile(r"[pv]-(\d{13})")                                # retro_kapsam.py:gun_of
_RE_GUN = re.compile(r"(20\d{6})")
_RE_CAM1 = re.compile(r"kamera(\d)")                                   # sera_pipeline.py:cam_of
_RE_CAM2 = re.compile(r"[/_]k(\d)[_-]")
_RE_KARDES_KOK = re.compile(r"_?\d{3}\.jpg$")                          # retro_build.py:en_iyi_kare
_RE_OLAY_KARE = re.compile(r"^(\d+)(_raw)?\.jpg$")


# ===================================================================== kaynak gezgini
def kaynaklar(arsiv=None):
    """Arşivin TAMAMI: zaman tüneli + tanılama + DVR HD kareleri + olay kanıtları.

    BİREBİR full_scan.py:kaynaklar(). Sıra ve süzgeçler korundu:
      · events altından SADECE `_raw` ya da adında `hd` geçen kareler alınır —
        çizili kare (canlı sistemin bbox bastığı kare) dedektöre GİRMEZ.
    -> mutlak yol listesi
    """
    AR = arsiv or ayar.ARSIV
    f = []
    f += sorted(glob.glob(os.path.join(AR, "timeline", "*", "*", "*.jpg")))
    f += sorted(glob.glob(os.path.join(AR, "diag_vps", "*.jpg")))
    f += sorted(glob.glob(os.path.join(AR, "diag_hd", "*.jpg")))
    f += sorted(glob.glob(os.path.join(AR, "harvest_hd", "frames", "*.jpg")))
    f += [p for p in sorted(glob.glob(os.path.join(AR, "events", "*", "*.jpg")))
          if "_raw" in p or "hd" in os.path.basename(p)]
    return f


def kaynak_adi(p):
    """Yol -> kaynak kovası adı. BİREBİR sera_pipeline.py:kaynak_adi."""
    if "/timeline/" in p:
        return "timeline"
    if "/harvest_hd/" in p:
        return "dvr_hd"
    if "/diag_hd/" in p:
        return "diag_hd"
    if "/diag_vps/" in p:
        return "diag_vps"
    if "/events/" in p:
        return "olay"
    return "?"


def kaynak_sayim(yollar):
    """{kaynak_adi: adet} — tarama başlarken 'ne tarıyoruz' logu için."""
    return dict(collections.Counter(kaynak_adi(p) for p in yollar))


def timeline_gunleri(cam=None, arsiv=None):
    """timeline/kameraN/YYYYMMDD dizinlerinden (cam, gun) listesi."""
    AR = arsiv or ayar.ARSIV
    desen = "kamera%s" % cam if cam else "*"
    out = []
    for d in sorted(glob.glob(os.path.join(AR, "timeline", desen, "20*"))):
        c = cam_of(d)
        if c is not None:
            out.append((c, os.path.basename(d)))
    return out


def gun_kareleri(cam, gun, arsiv=None):
    """Bir kamera-günün timeline kareleri: [(dakika, yol)]. BİREBİR degisim_anlari.py:gun_kareleri."""
    AR = arsiv or ayar.ARSIV
    ps = sorted(glob.glob(os.path.join(AR, "timeline", "kamera%d" % int(cam), str(gun), "*.jpg")))
    out = []
    for p in ps:
        b = os.path.basename(p)[:4]
        try:
            out.append((int(b[:2]) * 60 + int(b[2:]), p))
        except Exception:
            pass
    return out


# ===================================================================== yol -> kimlik
def cam_of(p):
    """Yoldan kamera numarası (1..5) veya None.

    BİREBİR sera_pipeline.py:cam_of — dört adlandırma şemasını da kapsayan üst küme:
      timeline/kamera3/... · diag_hd/kamera3_... · harvest_hd/frames/i_k3_... · /k4_...
    """
    m = _RE_CAM1.search(p) or _RE_CAM2.search(p)
    return int(m.group(1)) if m else None


def gun_of(p):
    """Yoldan gün 'YYYYMMDD' veya None. BİREBİR retro_kapsam.py:gun_of.

    ⚠ hacim_kuru.py:gun_of bilinmeyende "?" döndürüyordu. Oradan gelen çağrılar
    `gun_of(p) or "?"` yazmalı — sessiz davranış farkı olmasın diye not düşüldü.
    """
    if not p:
        return None
    m = _RE_GUN.search(p)
    if m:
        return m.group(1)
    m = _RE_OLAY.search(p)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, TZ).strftime("%Y%m%d")
    return None


def ts_of(p):
    """Dosya YOLUNDAN epoch-ms (TR saati varsayımıyla) veya None.

    Üç parser birleşti (mantık korunarak, sıra ÖNEMLİ):
      1. timeline  /YYYYMMDD/HHMM.jpg          ← retro_build.py:ts_timeline · retro_kapsam.py:ts_of
      2. hasat/diag  [k|kameraN]_YYYYMMDD-HHMMSS ← retro_build.py:ts_harvest (basename üzerinde)
      3. olay klasörü  p-<epoch_ms>-kameraN     ← retro_kapsam.py:gun_of'un ms yakalayıcısı

    ⚠ retro_build2.py'nin yazdığı ders: v1'in ts_timeline'ı SADECE 1. şemayı tanıyordu ve
      diag/harvest adlandırmasında sessizce None dönüyordu → full_scan A kovasının 92
      kaydından 54'ü çöpe gitti. Bu birleşik parser o hatayı kapatır.
    """
    if not p:
        return None
    m = _RE_TIMELINE.search(p)
    if m:
        g = m.group(1)
        return int(datetime(int(g[:4]), int(g[4:6]), int(g[6:8]),
                            int(m.group(2)), int(m.group(3)), tzinfo=TZ).timestamp() * 1000)
    m = _RE_HASAT.search(os.path.basename(p))
    if m:
        g, s = m.group(2), m.group(3)
        return int(datetime(int(g[:4]), int(g[4:6]), int(g[6:8]),
                            int(s[:2]), int(s[2:4]), int(s[4:6]), tzinfo=TZ).timestamp() * 1000)
    m = _RE_OLAY.search(p)
    if m:
        return int(m.group(1))
    return None


def ts_hasat(p):
    """DVR hasat kare adından (cam, epoch-ms). BİREBİR retro_build.py:ts_harvest.
    Kamerayı da dosya adından çıkarması gerektiği için ts_of'tan ayrı duruyor."""
    m = _RE_HASAT.search(os.path.basename(p))
    if not m:
        return None, None
    cam, g, s = int(m.group(1)), m.group(2), m.group(3)
    return cam, int(datetime(int(g[:4]), int(g[4:6]), int(g[6:8]),
                             int(s[:2]), int(s[2:4]), int(s[4:6]), tzinfo=TZ).timestamp() * 1000)


def zaman_of(p):
    """(gun 'YYYYMMDD', saat 'HHMM') — BİREBİR sera_pipeline.py:zaman_of.
    Dört adlandırma şeması karşılanır; çözülemezse (gun_of(p), None)."""
    b = os.path.basename(p)
    m = _RE_TIMELINE.search(p)
    if m:
        return m.group(1), m.group(2) + m.group(3)
    m = re.search(r"(20\d{6})-(\d{2})(\d{2})\d{2}", b)
    if m:
        return m.group(1), m.group(2) + m.group(3)
    m = re.search(r"p-(\d{13})-", p)
    if m:
        d = datetime.fromtimestamp(int(m.group(1)) / 1000.0, TZ)
        return d.strftime("%Y%m%d"), d.strftime("%H%M")
    return gun_of(p), None


def yerel_zaman(ts_ms, bicim="%Y-%m-%d %H:%M:%S"):
    """epoch-ms -> TR yerel saat metni."""
    return datetime.fromtimestamp(int(ts_ms) / 1000.0, TZ).strftime(bicim)


# ===================================================================== VPS <-> yerel yol
def vps2yerel(p, arsiv=None):
    """/opt/sera/... -> /mnt/data/sera-arsiv/...

    BİREBİR oof_sweep.py / train_verifier3.py / retro_build2.py'nin kullandığı basit replace.
    En güncel scriptlerin hepsi bunu kullanıyor; varsayılan budur.
    """
    AR = (arsiv or ayar.ARSIV).rstrip("/") + "/"
    return (p or "").replace(ayar.VPS_ONEK, AR)


def vps2yerel_diag(p, arsiv=None):
    """train_verifier.py:vps2local varyantı — /opt/sera/diag/ dizinini diag_vps/'ye eşler.

    ⚠ İki eşleme FARKLI: arşivde hem `diag/` hem `diag_vps/` var. Eski etiket kuyruğunu
    (labels_snapshot.json hattı) okuyan kod bu varyantı kullanıyordu; sayı tutmuyorsa
    önce hangi eşlemeyle üretildiğine bakın.
    """
    AR = (arsiv or ayar.ARSIV).rstrip("/")
    return ((p or "")
            .replace("/opt/sera/events", AR + "/events")
            .replace("/opt/sera/timeline", AR + "/timeline")
            .replace("/opt/sera/harvest_hd", AR + "/harvest_hd")
            .replace("/opt/sera/diag/", AR + "/diag_vps/"))


def yerel2vps(p, arsiv=None):
    """/mnt/data/sera-arsiv/... -> /opt/sera/...  (dağıtım/istemci tarafı için)"""
    AR = (arsiv or ayar.ARSIV).rstrip("/") + "/"
    return (p or "").replace(AR, ayar.VPS_ONEK)


def rel(p, arsiv=None):
    """Arşiv köküne göreli yol. retro_build.py'nin `rel` alanıyla aynı biçim.
    (İstemci ASLA yol göndermez, sunucu kayıttan okur — path-traversal dersi.)"""
    AR = (arsiv or ayar.ARSIV).rstrip("/") + "/"
    return (p or "").replace(AR, "")


def mutlak(r, arsiv=None):
    """Göreli ya da mutlak yolu mutlak yola çevir."""
    AR = arsiv or ayar.ARSIV
    if not r:
        return None
    return r if os.path.isabs(r) else os.path.join(AR, r)


# ===================================================================== sahne / gece
def sahne(kayit):
    """⚠ SIZINTI ÖNLEYİCİ GRUPLAMA — BİREBİR oof_sweep.py:sahne (train_verifier3.py de aynısı).

    NEDEN: aynı klipten/olaydan gelen kareler birbirinin kopyası. Rastgele CV yaparsan aynı
    sahne hem eğitimde hem testte olur ve %99 gibi SAHTE bir skor çıkar. GroupKFold bu
    anahtarla bölünür.

    kayit : etiket kuyruğu öğesi (eid / cam / gun / saat alanları)
    -> "e:<eid>"  ya da  "t:<cam>/<gun>/<saat[:3]>"   (~10 dakikalık kova)
    """
    if kayit.get("eid"):
        return "e:" + str(kayit["eid"])
    g, s = str(kayit.get("gun") or "?"), str(kayit.get("saat") or "?")
    return "t:%s/%s/%s" % (kayit.get("cam"), g, s[:3])


def sahne_klip(kayit):
    """FARKLI bir gruplama — BİREBİR train_verifier.py:sahne (select_next100.py de kullanır).

    fid'i `h_k3_20260729104233` gibi olan hasat kareleri KLİP bazında gruplanır; timeline
    kovası burada SAAT (dakika değil) genişliğindedir. sahne() ile karıştırmayın: aynı veri
    üzerinde farklı fold'lar üretir, dolayısıyla farklı sayı verir.
    """
    m = re.match(r"^h_(k\d_\d{8}\d{6})", kayit.get("fid") or "")
    if m:
        return "klip_" + m.group(1)
    if kayit.get("eid"):
        return "olay_" + kayit["eid"]
    g, s, c = kayit.get("gun"), kayit.get("saat"), kayit.get("cam")
    if g and s:
        return "tl_%s_%s_%s" % (c, g, s[:2])
    return "misc_%s" % c


def _saat_cikar(x):
    """Girdiden saat (0-23) çıkar. dict(kuyruk öğesi) / epoch-ms / 'HHMM' / datetime kabul eder."""
    if x is None:
        return None
    if isinstance(x, dict):
        s = str(x.get("saat") or "")[:2]
        if s.isdigit():
            return int(s)
        if x.get("ts"):
            return datetime.fromtimestamp(float(x["ts"]) / 1000.0, TZ).hour
        return None
    if isinstance(x, datetime):
        return x.astimezone(TZ).hour if x.tzinfo else x.hour
    if isinstance(x, (int, float)):
        # 13 haneli = ms, değilse saniye
        v = float(x)
        if v > 1e11:
            v /= 1000.0
        return datetime.fromtimestamp(v, TZ).hour
    s = str(x)
    if len(s) >= 2 and s[:2].isdigit():
        return int(s[:2])
    return None


def gece(x):
    """Gece mi? BİREBİR gece_sweep.py:gece — ÖLÇÜM tanımı: saat >= 20 veya < 6.

    Çözülemeyen girdide None döner (gece_sweep.py de None döndürüyordu; `== True` /
    `== False` maskeleri bu yüzden üçlü mantıkla yazılmıştı, öyle kalsın).
    """
    h = _saat_cikar(x)
    if h is None:
        return None
    return h >= ayar.GECE_BAS or h < ayar.GECE_BIT


def gece_uretim(x):
    """⚠ FARKLI TANIM: vps/person_watch_v3.py:is_night — 21:00-07:00 TR.

    Canlı kapıların (NIGHT_CONF / NIGHT_HD_CONF) hangi saatte devreye girdiğini
    sormak için bu kullanılır. Ölçüm tablolarında gece() kullanıldı; ikisini
    karıştırmak 20:00-21:00 ve 06:00-07:00 bantlarını yanlış kovaya atar.
    """
    h = _saat_cikar(x)
    if h is None:
        return None
    return h >= ayar.GECE_BAS_URETIM or h < ayar.GECE_BIT_URETIM


# ===================================================================== olay kareleri
def olay_dizin(eid, arsiv=None):
    return os.path.join(arsiv or ayar.ARSIV, "events", str(eid))


def olay_kareleri(eid, best=None, arsiv=None):
    """Bir olayın kanıt kareleri + PRE-ROLL uyarısı.

    Kaynak: olay_denetim2.py:kareleri_bul (ham/çizili ayrımı) +
            vps/person_watch_v3.py:1039 (pre-roll kuralı).

    ⚠ PRE-ROLL TUZAĞI — bu projede iki kez ölçüldü:
      1.jpg olayın ilk karesi DEĞİL, bir önceki poll'un karesidir (~POLL_S=20 sn ÖNCESİ).
      Kişi çoğu zaman daha kadraja girmemiştir. "Boş kare geliyor" şikâyetinin kaynağı buydu.
      Karar olayın TÜM karelerinin EN İYİSİYLE verilir; asla tek kareye bakılmaz.
      `best` (state kaydındaki alan) verilirse tespit karesinin indeksi ondan bilinir.

    ⚠ ÇİZİM TUZAĞI: `N.jpg` kareleri canlı sistemin bbox ÇİZDİĞİ karelerdir. Kırmızı
      çerçeve hem dedektörü bozar hem doğrulayıcı kırpmasına girer. `N_raw.jpg` varsa
      onu kullanın; yoksa sera.olay tarafındaki cizim_geri_al ile temizleyin.
      (Çizilen dikdörtgen CANLI SİSTEMİN GÖRDÜĞÜ KUTUDUR — bedava kutu, yedek olarak değerli.)

    -> [{"yol", "i", "ham", "hd", "preroll", "ad"}]  ·  ham kareler önce (denetim sırası)
    """
    d = olay_dizin(eid, arsiv)
    if not os.path.isdir(d):
        return []
    kayit = []
    numarali = []
    for ad in sorted(os.listdir(d)):
        if not ad.endswith(".jpg"):
            continue
        p = os.path.join(d, ad)
        if ad == "hd.jpg":
            kayit.append({"yol": p, "ad": ad, "i": None, "ham": True, "hd": True, "preroll": False})
            continue
        m = _RE_OLAY_KARE.match(ad)
        i = int(m.group(1)) if m else None
        r = {"yol": p, "ad": ad, "i": i, "ham": bool(m and m.group(2)), "hd": False, "preroll": None}
        kayit.append(r)
        if i is not None:
            numarali.append(r)
    if numarali:
        enb = max(r["i"] for r in numarali)
        esik = int(best) if best else (2 if enb >= 2 else None)
        for r in numarali:
            # best verilmişse kesin; verilmemişse ≥2 kare varken 1 numaralı kare pre-roll'dur
            r["preroll"] = (r["i"] < esik) if esik else False
    kayit.sort(key=lambda r: (not r["ham"], r["i"] is None, r["i"] or 0))
    return kayit


def olay_kareleri_ciftler(eid, arsiv=None):
    """BİREBİR olay_denetim2.py:kareleri_bul çıktısı: [(yol, ham_mi)].
    Ham (_raw) kareler önce, sonra çiziliyler. O dosyadan taşınan kod bunu çağırsın —
    davranış aynı kalır, pre-roll bilgisi isteyen olay_kareleri() kullanır.

    ⚠ BİLİNEN SAPMA (bilerek korundu): burası `hd.jpg`'yi ham=False sayar, oysa hd.jpg
      DVR ana-akışından curl'lenen ÇİZİMSİZ karedir (person_watch_v3.py:record_clip).
      Eski kod bu yüzden hd.jpg'yi de cizim_kutusu/temizle'den geçiriyordu — gereksiz iş
      ve olmayan çizgiyi "bulma" riski. olay_kareleri() bunu ham=True/hd=True olarak
      doğru işaretler. Sayıları yeniden üretirken bu fonksiyon, düzeltmek için o.
    """
    d = olay_dizin(eid, arsiv)
    if not os.path.isdir(d):
        return []
    ham = sorted(glob.glob(os.path.join(d, "*_raw.jpg")))
    cizili = sorted([p for p in glob.glob(os.path.join(d, "*.jpg")) if not p.endswith("_raw.jpg")])
    return [(p, True) for p in ham] + [(p, False) for p in cizili]


def kardes_kareler(yol, arsiv=None):
    """Aynı DVR hasat segmentinin TÜM kareleri (verilen kare dahil).

    BİREBİR retro_build.py:en_iyi_kare içindeki glob:
        kok = re.sub(r"_?\\d{3}\\.jpg$", "", basename);  harvest_hd/frames/<kok>*.jpg

    NEDEN VAR: hasat olaylarında `_001` çoğu zaman insanın henüz kadraja girmediği karedir;
    denetimde 5 kayıtta dedektör hiç kutu bulamadı çünkü kişi sonraki karelerdeydi.
    Temsilci kare = segmentin EN İYİSİ, ilki değil. (Çağıran skorlamayı kendi yapar.)
    -> sıralı yol listesi (segment tanınmazsa boş liste)
    """
    AR = arsiv or ayar.ARSIV
    b = os.path.basename(yol or "")
    kok = _RE_KARDES_KOK.sub("", b)
    if not kok or kok == b:
        return []
    return sorted(glob.glob(os.path.join(AR, "harvest_hd", "frames", kok + "*.jpg")))


def olaylastir(kayitlar, pencere_s=None):
    """(cam, ts) taşıyan kayıtları kamera içinde `pencere_s` boşluğuyla olaylara böl.

    BİREBİR retro_kapsam.py:olaylastir. Tekleştirme kuralı: aynı kamerada 6 dk (BIRLESTIR_S)
    içindeki kareler TEK olaydır — 437 kare 437 alarm değil, bir kişinin kadrajda geçirdiği süre.
    Temsilci kare olarak grubun en yüksek `dog_oof`'lusu tutulur.
    """
    P = ayar.BIRLESTIR_S if pencere_s is None else int(pencere_s)
    ks = sorted(kayitlar, key=lambda r: (r["cam"], r["ts"]))
    olay, son = [], {}
    for r in ks:
        c = r["cam"]
        if c in son and r["ts"] - son[c]["ts_son"] <= P * 1000:
            o = son[c]
            o["ts_son"] = r["ts"]; o["n"] += 1
            o["uyeler"].append(r)
            if r.get("dog_oof") is not None and r["dog_oof"] > (o.get("dog_oof") or -1):
                o["dog_oof"] = r["dog_oof"]; o["p"] = r["p"]; o["det"] = r.get("det")
            continue
        o = {"ts": r["ts"], "ts_son": r["ts"], "cam": c, "n": 1, "p": r.get("p"),
             "det": r.get("det"), "dog_oof": r.get("dog_oof"), "uyeler": [r]}
        olay.append(o); son[c] = o
    olay.sort(key=lambda o: o["ts"])
    return olay


# ===================================================================== etiket kuyruğu okuma
def kuyruk(yol=None):
    """Etiket kuyruğunu {fid: oge} olarak oku. Varsayılan 946'lık set (ayar.KUYRUK).
    Kaynak: train_verifier3.py / oof_esik.py'deki `{it["fid"]: it for it in ...["items"]}`."""
    import json
    with open(yol or ayar.KUYRUK) as f:
        return {it["fid"]: it for it in json.load(f)["items"]}


def etiketler(yol=None):
    """Etiketleri {fid: "var|yok|kutu|cok"} olarak oku (labels_946.json şeması: {"v": ...})."""
    import json
    with open(yol or ayar.ETIKET) as f:
        d = json.load(f)
    return {k: (v if isinstance(v, str) else v.get("v")) for k, v in d.items()}


def etiketli_kayitlar(kuyruk_yol=None, etiket_yol=None, arsiv=None, suphe=None):
    """Etiket + kuyruk + yerel yolu birleştirip skorlanabilir kayıt listesi üret.

    BİREBİR train_verifier3.py:main'in kayıt kurma döngüsü (aynı süzgeç sırası):
      şüpheli fid atla → kuyrukta yoksa atla → kutusu (pbox|kutu) yoksa atla →
      yerel dosya yoksa atla.
    -> [{"fid","p","box","cam","et","grup","hd"}]
    """
    q = kuyruk(kuyruk_yol)
    lab = etiketler(etiket_yol)
    sup = set(suphe or ())
    AR = arsiv or ayar.ARSIV
    out = []
    for fid, et in lab.items():
        if fid in sup:
            continue
        it = q.get(fid)
        if not it:
            continue
        box = it.get("pbox") or it.get("kutu")
        if not box:
            continue
        p = vps2yerel(it.get("p") or "", AR)
        if not p or not os.path.exists(p):
            continue
        out.append({"fid": fid, "p": p, "box": box, "cam": it.get("cam"),
                    "et": et, "grup": sahne(it), "hd": bool(it.get("hd"))})
    return out


# ===================================================================== özet
def ozet(yaz=True):
    """Arşivin kaba envanteri — 'ne var elimizde' sorusunun tek satırlık cevabı."""
    f = kaynaklar()
    d = {"toplam_kare": len(f), "kaynak": kaynak_sayim(f),
         "olay_klasoru": len(glob.glob(os.path.join(ayar.ARSIV, "events", "*"))),
         "timeline_gun": len(set(g for _, g in timeline_gunleri())),
         "kamera": sorted(set(c for c in (cam_of(p) for p in f) if c))}
    if yaz:
        print("=== arşiv özeti (%s) ===" % ayar.ARSIV)
        for k, v in d.items():
            print("  %-14s %s" % (k, v))
    return d


if __name__ == "__main__":
    ozet()

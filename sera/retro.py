# -*- coding: utf-8 -*-
"""
sera.retro — "SONRADAN BULUNDU" HATTININ TAMAMI (2 Ağu 2026).

Canlı sistem o an göremediği insanları arşivden geriye dönük bulur. Bu modül o hattın
tek uygulamasıdır: aday üretimi → tekleştirme → temsilci kare → canlı çakışma → denetim →
animasyon → kapsam taraması → dosyaya yazma.

DEVRALINAN (mantık BİREBİR korundu, sayı kaymadı):
  ts_timeline()      ← retro_build.py:31          (⚠ EKSİK parser — aşağıdaki nota bak)
  adaylar()          ← retro_build.py:main 1. bölüm + retro_build2.py:main 1. bölüm
  kural_kademeli()   ← retro_build2.py:kural  (= retro_kapsam.json:onerilen_kural)
  teklestir()        ← retro_build.py:main tekleştirme + retro_build2.py:main 2. bölüm
  en_iyi_kare()      ← retro_build.py:en_iyi_kare (retro_build2.py'de aynısı)
  canli_cakisma()    ← retro_build2.py:main 3. bölüm (yakin/bisect)
  etiketle_ele()     ← retro_build2.py:main "etiketle KANITLANMIS yanlis"
  denetle()          ← retro_denetim2.py:main  (v1 = retro_denetim.py DEĞİL — aşağıya bak)
  animasyon()        ← retro_anim.py:main
  kapsam_taramasi()  ← retro_kapsam.py:main 3. bölüm (IZGARA) + biliniyor/ziyaret_biliniyor
  oneri()            ← retro_kapsam.py'nin YAZDIĞI rapor okunur — YENİDEN ÖLÇÜLMEZ
  tavan()            ← retro_tavan.py:main  (taban hata + örnekleme tavanı + gerçek yakalama)
  pano()             ← retro_pano.py:main + retro_pano2.py:main (çizim sera.gorsel'e devredildi)
  pano_zoom()        ← retro_zoom.py:main
  dosyaya_yaz()      ← retro_build.py:main çıktı + retro_build2.py:main 4. bölüm

⚠ KORUNAN İKİ HATA (bilerek; geçmiş sayıları yeniden üretebilmek için):
  1. ts_timeline() SADECE `/YYYYMMDD/HHMM.jpg` şemasını tanır. full_scan A kovasının
     91 uygun kaydından 38'i geçer, 53'ü SESSİZCE düşer. v1'in 67 olayı bu yüzden 67'dir.
     Düzeltilmişi arsiv.ts_of() (üç şema birleşik) — v2 hattı onu kullanır.
     `adaylar(..., v1_zaman=True)` eski davranışı ister.
  2. retro_denetim.py (v1 denetim) kareyi ÇEYREKLERE bölüp skorluyordu; küçük insan
     çeyreğin içinde seyreldiği için 67'nin 22'sini "şüpheli" ilan etti — yöntemin kendi
     körlüğü, kanıt değil. Bu modülde SADECE v2 (KUTUYLA skorlama) uygulanır; çeyrek
     kırpma taşınmadı.

⚠ ÖLÇÜM TOTOLOJİSİ UYARISI — denetle() okurken:
  Üretim doğrulayıcı kafası bu karelerin çoğuyla eğitildi. `govde="dogrulayici"` ile
  yapılan denetim BAĞIMSIZ DEĞİLDİR; kendi eğitim setini onaylar. Bağımsız olan iki yol:
    · gün-dışla skor (dog_oof) — gate/retro_kapsam_skor.json'da hazır
    · üç bağımsız gövde (dinov2/clip/siglip) — govde="uc" (retro_denetim2.py'nin yaptığı)
  Arşivde dog>=0.80 diyen kare: canlı skorla 95, gün-dışla 74. Aradaki fark totoloji payı.

⚠ RETRO NEDEN BU KADAR İŞ ÜRETİYOR — kökü canlı hatta (bu modül düzeltmez, belgeler):
  vps/person_watch_v3.py:  `if do_fire and _verifier is not None and det_box:`
  Şüpheli kapıları (hd-red / tekrar-statik / cok-olcek) ateşi kestiğinde DOĞRULAYICI HİÇ
  ÇALIŞMIYOR — AUC 0.98'lik model tam gerektiği yerde devre dışı. Ölçüldü: doğrulayıcı
  >=0.50 ile ateşlenseydi 14 GERÇEK insan kurtulur, 0 yanlış geçerdi (OOF ve olay-dışla
  LOEO, iki bağımsız skorlama aynı sonucu veriyor). En zararlı kapı tekrar-statik:
  7'nin 6'sı gerçek insan. Retro havuzunun bir kısmı bu kapının ürünüdür; kapı düzelirse
  o kayıtlar CANLI yakalanır ve retro'ya hiç düşmez. Düzeltme yeri sera/olay.py + üretim.

REDDEDİLEN SİNYALLER (ölçüldü, kullanılmıyor — yeniden denemeyin):
  · arka-plan referansı / NCC → gate/arkaplan_ref.json: veto testi AKTİF ZARAR
    (yakalama -2.01 puan, yanlış +1.19 puan; 300 turun 0'ında ikisi birden iyileşmedi)
  · zamansal tutarlılık / hareket → gate/zamansal.json: katkı yok, eşleştirilmiş
    noktada KÖTÜ (+17.96 FP)

4G MALİYETİ: bu modül DVR'dan indirme YAPMAZ. animasyon() bile diskteki hasat karelerinden
kurulur (ince hasat segment başına 63 kareye kadar indirmişti, hepsi duruyor).

Kullanım:
    from sera import retro
    olaylar, rapor = retro.v1_havuzu()          # mevcut 67'yi yeniden üret
    olaylar, rapor = retro.v2_havuzu()          # genişletilmiş 76'lık havuz
    retro.dosyaya_yaz(olaylar, "/tmp/retro.json", uretim="sera.retro")
    retro.pano("yeni"); retro.pano("v1")        # görsel denetim + KIYAS TABANI
    retro.tavan()                               # eşikten bağımsız yapısal sınırlar

Doğrulama:
    python -m sera.retro --dogrula        # v1'i yeniden üret, retro_events.json ile kıyasla
    python -m sera.retro --ozet           # diskteki havuzların envanteri
    python -m sera.retro --kapsam         # eşik ızgarası
    python -m sera.retro --tavan          # yapısal tavan (gate/retro_tavan.json yazar)
    python -m sera.retro --pano yeni      # kontakt sayfası
"""
import os
import re
import json
import glob
import bisect
import random
import collections

from . import ayar
from . import arsiv

# ============================================================================ yollar
ARSIV = ayar.ARSIV
GATE = ayar.GATE

RETRO_V1 = ayar.gate("retro_events.json")            # retro_build.py çıktısı (uygulamada canlı)
RETRO_V2 = ayar.gate("retro_events2.json")           # retro_build2.py çıktısı (henüz aktarılmadı)
KAPSAM = ayar.gate("retro_kapsam.json")              # retro_kapsam.py raporu
KAPSAM_SKOR = ayar.gate("retro_kapsam_skor.json")    # per-kayıt det/dog_canli/dog_oof/uzlasma
FULL_SCAN = ayar.gate("full_scan.json")              # A kovası = v1'in skorlu kaynağı
HACIM_KURU = ayar.gate("hacim_kuru.json")            # timeline kutuları
HACIM_DIAG = ayar.gate("hacim_diag.json")            # diag kutuları
DENETIM_V2 = ayar.gate("retro_denetim2.json")
GOMU3 = ayar.gate("gomu3.npz")                       # 3 gövde gömüsü (govde="uc" için)
EV_NOW = os.path.join(ayar.SCRATCH, "ev_now.json")   # canlı state anlık görüntüsü

HASAT_DIZIN = ayar.yol("harvest_hd", "frames")
ANIM_DIZIN = ayar.yol("retro_anim")

# ============================================================================ eşikler
# kaynak: retro_build.py:DOG_ESIK — geçmişe yazarken temkinli ol
DOG_ESIK_RETRO = ayar.DOG_ESIK_RETRO          # 0.80
# kaynak: retro_build2.py:DOG_ESIK / DET_GUCLU / UZLASMA_GEREK — ÖLÇÜLEN kademeli kural
DOG_ESIK_KADEMELI = ayar.DOG_ESIK_KADEMELI    # 0.70
DET_GUCLU = ayar.DET_GUCLU                    # 0.20
UZLASMA_GEREK = ayar.UZLASMA_GEREK            # 2
DET_ATES = ayar.DET_ATES                      # 0.52 — üretimin ateşleme eşiği
BIRLESTIR_S = ayar.BIRLESTIR_S                # 360 — aynı kamerada 6 dk = tek olay
CANLI_PENCERE_S = ayar.CANLI_PENCERE_S        # 360
V1_PENCERE_S = ayar.V1_PENCERE_S              # 360
ZIYARET_PENCERE_S = ayar.ZIYARET_PENCERE_S    # 600

# kaynak: retro_anim.py:20
MIN_KARE, MAKS_KARE, ANIM_GENIS, ANIM_SURE_MS = 5, 30, 560, 200
ANIM_KALITE, ANIM_METOD = 68, 4

# kaynak: retro_denetim2.py:main — üç gövde ortalamasının kova sınırları
DENETIM_SAGLAM = 0.50
DENETIM_SUPHELI = 0.20

# kaynak: retro_tavan.py:PENCERE_S — timeline 5 dk aralıklı, ±2.5 dk = en yakın kare
TAVAN_PENCERE_S = 150
TAVAN_DET_IZGARA = (0.52, 0.35, 0.20, 0.10, 0.05)
TAVAN_DOG_IZGARA = (0.80, 0.50, 0.30)
TAVAN_JSON = ayar.gate("retro_tavan.json")

# kaynak: retro_pano2.py (havuz kovaları) / retro_pano.py (kapsam kovaları)
PANO_N = 25
PANO_N_KAPSAM = 48

POZ_ETIKET = ("var", "cok", "kutu")           # kare düzeyinde "insan VAR" — retro_build2.py:POZ

# v1'in TEK tanıdığı zaman şeması (retro_build.py:ts_timeline)
_RE_V1_TIMELINE = re.compile(r"/(20\d{6})/(\d{4})\.jpg$")
_RE_SEGMENT_KOK = re.compile(r"_?\d{3}\.jpg$")

_LANCZOS = 4          # cv2.INTER_LANCZOS4 — retro_zoom.py'nin kullandığı (cv2 importsuz sabit)

_DED = None


def _dedektor():
    """Süreç-ömürlü tek dedektör (346 MB'lık oturumlar iki kez açılmasın)."""
    global _DED
    if _DED is None:
        from . import dedektor as _d
        _DED = _d.varsayilan()
    return _DED


# ============================================================================ zaman
def ts_timeline(p):
    """⚠ v1'in EKSİK zaman parser'ı — BİREBİR retro_build.py:ts_timeline.

    Sadece `/YYYYMMDD/HHMM.jpg` tanır; diag/harvest adlandırmasında None döner ve kayıt
    sessizce çöpe gider (full_scan A kovasında 91 → 38). Bu fonksiyon SADECE eski sayıları
    yeniden üretmek için durur. Yeni kod arsiv.ts_of() kullanır (üç şema birleşik).
    """
    from datetime import datetime
    m = _RE_V1_TIMELINE.search(p or "")
    if not m:
        return None
    g, s = m.group(1), m.group(2)
    return int(datetime(int(g[:4]), int(g[4:6]), int(g[6:8]),
                        int(s[:2]), int(s[2:]), tzinfo=arsiv.TZ).timestamp() * 1000)


def ts_hasat(p):
    """DVR hasat kare adından (cam, epoch-ms) — arsiv.ts_hasat'ın yeniden ihracı."""
    return arsiv.ts_hasat(p)


# ============================================================================ kural
def kural_kademeli(r, dog_esik=None, det_guclu=None, uzlasma_gerek=None):
    """ÖLÇÜLEN kademeli kural — BİREBİR retro_build2.py:kural.

        dog_oof >= 0.70  VE  (det >= 0.20  VEYA  3 gövdeden 2'si onaylıyor)

    GEREKÇE (gate/retro_kapsam.json:uzlasma_etiketli): zayıf kutu bandında etiketli
    kesinlik etiketsiz bölgeye TAŞINMIYOR. 2/3 uzlaşmanın etiketli kesinliği %100 (n=14),
    1/3'ünki %63 (n=30). Eşleştirilmiş çalışma noktasında (ikisi de gün-dışla skor, ikisi
    de det<0.52 etiketli bölge): TABAN TP 9 / FP 1 · BU KURAL TP 11 / FP 0.
    """
    de = DOG_ESIK_KADEMELI if dog_esik is None else dog_esik
    dg = DET_GUCLU if det_guclu is None else det_guclu
    uz = UZLASMA_GEREK if uzlasma_gerek is None else uzlasma_gerek
    v = r.get("dog_oof")
    if v is None or v < de:
        return False
    d = r.get("det")
    if d is not None and d >= dg:
        return True
    return (r.get("uzlasma") or 0) >= uz


# ============================================================================ yardımcı okuma
def hacim_kutulari(yollar=None):
    """{mutlak_yol: [x1,y1,x2,y2]} — taramada bulunmuş kutular.
    Kaynak: retro_build2.py / retro_pano2.py / retro_zoom.py'nin aynı iki dosyayı okuması."""
    out = {}
    for f in (yollar or (HACIM_KURU, HACIM_DIAG)):
        if not os.path.exists(f):
            continue
        with open(f) as fh:
            for r in json.load(fh)["kayit"]:
                out[r["p"]] = r.get("box")
    return out


def kapsam_skorlari(yol=None, arsiv_=None):
    """gate/retro_kapsam_skor.json — retro_kapsam.py'nin ürettiği PER-KAYIT skorlar.

    Alanlar: p(göreli) · cam · ts · det · dog_canli · dog_oof(GÜN-DIŞLA) · uzlasma · kaynak.
    Burada YENİDEN ÇIKARIM YAPILMAZ — aynı sayı iki kez üretilmesin, denetlenebilir kalsın
    (retro_build2.py'nin aldığı karar; ölçüm dosyası tek gerçek kaynak).
    -> [{... , "p": MUTLAK yol, "rel": göreli yol}]
    """
    AR = arsiv_ or ARSIV
    with open(yol or KAPSAM_SKOR) as f:
        d = json.load(f)
    out = []
    for r in d["kayit"]:
        r = dict(r)
        r["rel"] = r["p"]
        r["p"] = os.path.join(AR, r["p"])
        out.append(r)
    return out


def canli_kayitlar(yol=None, retro_haric=True, tur="person", cam_gerek=True):
    """Canlı state olayları. Kaynak: retro_build2.py/retro_kapsam.py'nin ev_now.json okuması.

    retro_haric=True → `retro: true` işaretli kayıtlar ATILIR; "bu anı canlı sistem
    gerçekten yakaladı mı" sorusu sadece gerçek canlı yakalamalarla sorulur.
    cam_gerek=False  → kamerası olmayan olaylar da döner (tavan() taban-hata kesişimi
                       retro_tavan.py'de kamerasızları da sayıyordu; sayı kaymasın).
    """
    with open(yol or EV_NOW) as f:
        d = json.load(f)
    ev = d.get("events", d) if isinstance(d, dict) else d
    out = [e for e in ev if e.get("kind") == tur and (e.get("cam") or not cam_gerek)]
    if retro_haric:
        out = [e for e in out if not e.get("retro")]
    return out


def canli_ziyaretler(yol=None):
    """ev_now.json'daki ziyaret kayıtları (`visits`). Kaynak: retro_tavan.py:main."""
    with open(yol or EV_NOW) as f:
        d = json.load(f)
    return d.get("visits", []) if isinstance(d, dict) else []


def olay_denetimi(yol=None):
    """gate/labels.json — Alperen'in olay bazlı TP/FP denetimi (119 kayıt).

    ⚠ ADI TUZAK: bu bir ETİKET SETİ DEĞİL. Kare etiketleri etiket.yukle()'dedir
    (946/763). Buradaki değerler "TP"/"FP" ve anahtar OLAY id'sidir.
    -> {eid: "TP"|"FP"}
    """
    with open(yol or ayar.DENETIM) as f:
        d = json.load(f)
    return {k: (v["v"] if isinstance(v, dict) else v) for k, v in d.items()}


def etiket_yollari(surum=None):
    """{mutlak_yol: 'var|yok|kutu|cok'} — Alperen'in etiketleri, MODEL ÇIKTISI DEĞİL.
    Kaynak: retro_build2.py:etiketler (orada 763'lük anlık görüntü kullanılmıştı).

    surum: "946" (ASIL) · "763" (v2'nin gördüğü) · doğrudan dosya yolu.
    """
    from . import etiket as _et
    lab = _et.yukle(surum)
    q = _et.kuyruk(surum)
    out = {}
    for f, e in lab.items():
        it = q.get(f)
        if not it:
            continue
        p = arsiv.vps2yerel(it.get("p") or "")
        if p:
            out[p] = e.get("v") if isinstance(e, dict) else e
    return out


# ============================================================================ 1) ADAYLAR
def adaylar(det_esik=None, dog_esik=None, kaynaklar=None, kural=None,
            v1_zaman=False, arsiv_=None, kutular=None, sessiz=False):
    """Retro aday KARELERİ üret (henüz olay değil, tek tek kareler).

    Üç kova var; hangisinin kullanılacağını `kaynaklar` seçer:

      "full_scan" — gate/full_scan.json A kovası. Dedektör ateşleme eşiğinin (0.52)
                    ALTINDA kalmış ama doğrulayıcı yüksek olan kareler. v1'in skorlu
                    tek kaynağı. Süzgeç: vskor >= dog_esik, cam var, zaman çözülüyor.
                    ⚠ v1 burada det süzgeci UYGULAMADI (det_esik=None geçin).

      "skor"      — gate/retro_kapsam_skor.json (timeline + diag_vps + diag_hd).
                    dog_oof GÜN-DIŞLA skordur; karar bununla verilir, canlı skorla değil.
                    v1 bu kovayı ve diag dizinlerini HİÇ görmüyordu.

      "hasat"     — harvest_hd/frames/*.jpg. KOŞULSUZ girer, hiçbir doğrulayıcı kapısı yok:
                    bu kareler zaten "insan bulundu" diye DVR'dan derin çekilmiş ve
                    timeline'ın hiç olmadığı kör günlerin (16/17/30/31 Tem) TEK kaynağı.
                    Mantık v1'den değişmedi. Bedeli: etiketli kesişimdeki 4 yanlışın 4'ü
                    de bu kovadan çıktı (bkz. etiketle_ele).

    det_esik / dog_esik : "full_scan" ve "skor" kovalarındaki eşikler. None = süzgeç yok.
    kural    : callable(kayit)->bool. Verilirse eşikler yerine bu uygulanır ("skor" kovası
               için kademeli kural: kural=kural_kademeli).
    v1_zaman : True → ts_timeline() (EKSİK parser, v1 davranışı). False → arsiv.ts_of().

    -> [{"ts","cam","det","dog","dog_oof","uzlasma","kaynak","p","box"}]
    """
    AR = arsiv_ or ARSIV
    kv = tuple(kaynaklar or ("skor", "hasat"))
    KUT = hacim_kutulari() if kutular is None else kutular
    zaman = ts_timeline if v1_zaman else arsiv.ts_of
    ham = []

    # ---------------------------------------------------------------- full_scan A kovası
    if "full_scan" in kv:
        with open(FULL_SCAN) as f:
            fs = json.load(f)
        dusen = 0
        for r in fs.get("A", []):
            if not r.get("cam"):
                continue
            if dog_esik is not None and (r.get("vskor") or 0) < dog_esik:
                continue
            if det_esik is not None and (r.get("dets") or 0) < det_esik:
                continue
            t = zaman(r["p"])
            if not t:
                dusen += 1
                continue
            ham.append({"ts": int(t), "cam": int(r["cam"]), "det": float(r.get("dets") or 0),
                        "dog": float(r["vskor"]), "dog_oof": None, "uzlasma": -1,
                        "kaynak": "arsiv-tarama", "p": r["p"],
                        "box": r.get("box") or KUT.get(r["p"])})
        if dusen and not sessiz:
            print("  full_scan: zaman damgasi cozulemeyen %d kayit DUSTU%s"
                  % (dusen, " (v1 davranisi)" if v1_zaman else ""))

    # ---------------------------------------------------------------- skorlu tarama
    if "skor" in kv:
        for r in kapsam_skorlari(arsiv_=AR):
            if not r.get("ts") or not r.get("cam"):
                continue
            if kural is not None:
                if not kural(r):
                    continue
            else:
                if dog_esik is not None and (r.get("dog_oof") or 0) < dog_esik:
                    continue
                if det_esik is not None and (r.get("det") or 0) < det_esik:
                    continue
            ham.append({"ts": int(r["ts"]), "cam": int(r["cam"]), "det": float(r["det"]),
                        "dog": float(r["dog_canli"]), "dog_oof": float(r["dog_oof"]),
                        "uzlasma": int(r.get("uzlasma", -1)),
                        "kaynak": "arsiv-tarama" if r["kaynak"] == "timeline" else "diag-tarama",
                        "p": r["p"], "box": KUT.get(r["p"])})

    # ---------------------------------------------------------------- DVR ince hasadı
    if "hasat" in kv:
        for p in sorted(glob.glob(os.path.join(AR, "harvest_hd", "frames", "*.jpg"))):
            cam, t = arsiv.ts_hasat(p)
            if cam and t:
                ham.append({"ts": int(t), "cam": int(cam), "det": None, "dog": None,
                            "dog_oof": None, "uzlasma": -1, "kaynak": "dvr-hasat",
                            "p": p, "box": KUT.get(p)})

    if not sessiz:
        print("ADAY KARE: %d  %s" % (len(ham), dict(collections.Counter(r["kaynak"] for r in ham))))
    return ham


# ============================================================================ 2) TEKLEŞTİRME
def teklestir(adaylar_, pencere_s=None, skor_alani="dog_oof",
              tasi=("dog", "det", "p", "box", "uzlasma", "kaynak"),
              uyeleri_tut=True):
    """Aynı kamerada `pencere_s` içindeki kareler TEK olaydır.

    BİREBİR retro_build.py / retro_build2.py tekleştirmesi. 437 kare 437 alarm değil,
    bir kişinin kadrajda geçirdiği süredir.

    skor_alani : temsilci kare hangi skora göre seçilir.
                 v1 → "dog"      (canlı doğrulayıcı skoru)
                 v2 → "dog_oof"  (GÜN-DIŞLA skor; hasat kaydında None olduğu için
                                  skorlu bir temsilciyi ASLA ezmez)
    tasi       : temsilci değişince olaya kopyalanacak alanlar.
                 v1 SADECE ("p",) kopyalıyordu — det/kaynak ilk üyeden kalıyordu.
                 v2 hepsini kopyalar. Fark bilerek parametre; ikisinin de geçmiş ölçümü var.

    ⚠ v1 `if r["dog"] and ...` (truthiness) yazıyordu, burada `is not None`. dog ya None'dır
      (hasat) ya da dog_esik>0 süzgecinden geçmiştir; iki koşul bu veride AYNI sonucu verir.

    -> [{... , "ts_son", "n", "uyeler"}]  ts'ye göre sıralı
    """
    P = BIRLESTIR_S if pencere_s is None else int(pencere_s)
    ks = sorted(adaylar_, key=lambda r: (r["cam"], r["ts"]))
    olay, son = [], {}
    for r in ks:
        c = r["cam"]
        o = son.get(c)
        if o is not None and r["ts"] - o["ts_son"] <= P * 1000:
            o["ts_son"] = r["ts"]
            o["n"] += 1
            if uyeleri_tut:
                o["uyeler"].append(r)
            v = r.get(skor_alani)
            mevcut = o.get(skor_alani)
            if v is not None and (mevcut is None or v > mevcut):
                o[skor_alani] = v
                for k in tasi:
                    if k != skor_alani:
                        o[k] = r.get(k)
            continue
        o = dict(r)
        o["ts_son"] = r["ts"]
        o["n"] = 1
        if uyeleri_tut:
            o["uyeler"] = [r]
        olay.append(o)
        son[c] = o
    olay.sort(key=lambda o: o["ts"])
    return olay


# ============================================================================ 3) TEMSİLCİ KARE
def en_iyi_kare(olay, dedektor=None, arsiv_=None, min_kardes=2):
    """Bir olayın DVR segmentindeki EN İYİ kareyi bul — PRE-ROLL tuzağının panzehiri.

    BİREBİR retro_build.py:en_iyi_kare (retro_build2.py'de aynısı).

    ⚠ NEDEN: hasat segmentinde `_001` çoğu zaman kişinin henüz kadraja girmediği karedir.
      Denetimde 5 kayıtta dedektör hiç kutu bulamadı — kişi sonraki karelerdeydi, fotoğraf
      da boş görünüyordu. Temsilci = segmentin EN İYİSİ, ilki DEĞİL.
      (Aynı tuzak canlı olaylarda da var: events/<eid>/1.jpg pre-roll'dur — bkz. arsiv.olay_kareleri.)

    Skorlama sera.dedektor.skor ile yapılır; retro_build.py'nin gömülü skor() fonksiyonuyla
    BİT-BİREBİR aynı sonucu verir (esik 0.03 · min_alan 0.0018 · person sınıfı 0).

    -> {"yol", "det", "kardes", "degisti"}   ·   kardeş yoksa mevcut kare geri döner
    """
    d = dedektor or _dedektor()
    p0 = olay.get("p") or arsiv.mutlak(olay.get("rel"), arsiv_)
    kardes = arsiv.kardes_kareler(p0, arsiv_)
    if len(kardes) < min_kardes:
        return {"yol": p0, "det": None, "kardes": len(kardes), "degisti": False}
    en, ep = -1.0, None
    for p in kardes:
        s = d.skor(p)
        if s > en:                       # eşitlikte İLK kare kazanır (v1 davranışı)
            en, ep = s, p
    return {"yol": ep, "det": round(en, 3), "kardes": len(kardes),
            "degisti": bool(ep and ep != p0)}


def en_iyi_kareler(olaylar, sadece_kaynak="dvr-hasat", uygula=True, dedektor=None,
                   arsiv_=None, sessiz=False):
    """en_iyi_kare()'yi havuza uygula. BİREBİR retro_build.py:en_iyi_kare döngüsü.

    sadece_kaynak="dvr-hasat" → yalnız hasat olayları (skorlu kovada temsilci zaten
    dog_oof'la seçildi, dedektörle yeniden seçmek mantığı değiştirirdi).
    -> temsilcisi DEĞİŞEN olay sayısı
    """
    d = dedektor or _dedektor()
    n = 0
    for o in olaylar:
        if sadece_kaynak and o.get("kaynak") != sadece_kaynak:
            continue
        r = en_iyi_kare(o, d, arsiv_)
        if uygula and r["degisti"]:
            o["p"] = r["yol"]
            o["det_kare"] = r["det"]
            n += 1
    if not sessiz:
        print("temsilci kare degistirilen olay: %d" % n)
    return n


# ============================================================================ 4) ÇAKIŞMA
def zaman_tablosu(kayitlar, cam_al=None, ts_al=None):
    """{cam: sıralı ts listesi} — bisect'li çakışma sorgusunun indeksi."""
    ca = cam_al or (lambda e: e.get("cam"))
    ta = ts_al or (lambda e: e.get("ts"))
    tab = collections.defaultdict(list)
    for e in kayitlar:
        c, t = ca(e), ta(e)
        if c is None or t is None:
            continue
        tab[int(c)].append(int(t))
    for c in tab:
        tab[c].sort()
    return dict(tab)


def yakin(tablo, cam, ts, pencere_s):
    """`tablo`da (cam, ts)'ye `pencere_s` içinde kayıt var mı? BİREBİR retro_build2.py:yakin."""
    a = tablo.get(int(cam)) or []
    i = bisect.bisect_left(a, int(ts))
    for j in (i - 1, i):
        if 0 <= j < len(a) and abs(a[j] - int(ts)) <= pencere_s * 1000:
            return True
    return False


def canli_cakisma(olaylar, canli_olaylar, pencere_s=None, alan="canli_ortusen", ele=True):
    """Canlı sistemin O AN yakaladığı anlar retro sayılmasın.

    BİREBİR retro_build2.py 3. bölüm. v1'de bu kontrol HİÇ YOKTU: v1 havuzunun 67
    kaydından 13'ü canlı olayla çakışıyormuş — yani "sonradan bulundu" diye gösterilen
    13 an aslında o an zaten yakalanmıştı.

    Her olaya `alan` (varsayılan "canli_ortusen") bayrağı YERİNDE yazılır.
    ele=True → çakışmayanların listesi döner (elenenler: [o for o in olaylar if o[alan]]).
    """
    P = CANLI_PENCERE_S if pencere_s is None else int(pencere_s)
    tab = zaman_tablosu(canli_olaylar)
    for o in olaylar:
        o[alan] = yakin(tab, o["cam"], o["ts"], P)
    return [o for o in olaylar if not o[alan]] if ele else olaylar


def havuz_cakisma(olaylar, referans, pencere_s=None, alan="v1_ortusen"):
    """Başka bir retro havuzuyla çakışma (aynı olay yeniden "yeni" sayılmasın).
    BİREBİR retro_build2.py'nin v1_ortusen hesabı. Bayrağı yerine yazar, listeyi döndürür."""
    P = V1_PENCERE_S if pencere_s is None else int(pencere_s)
    tab = zaman_tablosu(referans)
    for o in olaylar:
        o[alan] = yakin(tab, o["cam"], o["ts"], P)
    return olaylar


# ============================================================================ 5) ETİKETLE ELEME
def etiketle_ele(olaylar, etiket=None, surum=None, en_az=5, kaynak="dvr-hasat",
                 arsiv_=None, sessiz=False):
    """Kare kare "yok" etiketlenmiş DVR segmentlerini havuzdan at.

    BİREBİR retro_build2.py'nin "etiketle KANITLANMIS yanlis" adımı. Bu bir MODEL kararı
    değil, YER GERÇEĞİ: segmentte >= `en_az` etiket var ve hiçbiri pozitif değil.

    ⚠ DÜRÜSTLÜK NOTU (retro_build2.py'nin kendi uyarısı): bu iki kaydı etiketle attıktan
      SONRA aynı etiketlerle ölçülen kesinlik artık bağımsız değildir. Manşet rakam
      ATMADAN ÖNCEKİdir.

    -> (kalan_olaylar, atilan_rapor)
    """
    ET = etiket if etiket is not None else etiket_yollari(surum)
    AR = arsiv_ or ARSIV
    kalan, atilan = [], []
    for o in olaylar:
        if kaynak and o.get("kaynak") != kaynak:
            kalan.append(o)
            continue
        kok = _RE_SEGMENT_KOK.sub("", os.path.basename(o.get("p") or ""))
        kardes = sorted(glob.glob(os.path.join(AR, "harvest_hd", "frames", kok + "*.jpg")))
        et = [ET[p] for p in kardes if p in ET]
        if len(et) >= en_az and not any(v in POZ_ETIKET for v in et):
            atilan.append({"segment": kok, "kare": len(kardes), "etiketli": len(et),
                           "pozitif": 0, "ts": o["ts"], "cam": o["cam"]})
            continue
        kalan.append(o)
    if not sessiz:
        print("etiketle KANITLANMIS yanlis hasat segmenti atildi: %d -> %s"
              % (len(atilan), [a["segment"] for a in atilan]))
    return kalan, atilan


def etiket_kesinligi(olaylar, etiket=None, surum=None):
    """Temsilci karesi etiketli olan olaylarda kesinlik. BİREBİR retro_build2.py:kesinlik.
    -> {"etiketli","pozitif","yanlis","kesinlik","yanlis_kayit"}"""
    ET = etiket if etiket is not None else etiket_yollari(surum)
    n = poz = 0
    yanlis = []
    for o in olaylar:
        v = ET.get(o.get("p"))
        if v is None:
            continue
        n += 1
        if v in POZ_ETIKET:
            poz += 1
        else:
            yanlis.append(arsiv.rel(o["p"]))
    return {"etiketli": n, "pozitif": poz, "yanlis": n - poz,
            "kesinlik": poz / max(1, n), "yanlis_kayit": yanlis}


# ============================================================================ 6) DENETİM
def denetle(olaylar, ornek=None, govde="dogrulayici", tohum=20260802,
            esik_saglam=None, esik_supheli=None, det_esik=None, min_alan=None,
            kutu="dedektor", kafa_json=None, arsiv_=None, ilerleme=15,
            cikti=None, sessiz=False):
    """Retro kayıtları KUTUYLA yeniden skorla — takvimde yanlış "sonradan bulundu" kalmasın.

    BİREBİR retro_denetim2.py. Yöntemin özü:
      üretim dedektörünü ÇOK DÜŞÜK eşikle çalıştır (amaç ateşlemek değil, KUTU üretmek),
      sonra o kutuyu doğrulayıcıya ver.

    ⚠ v1 (retro_denetim.py) kareyi tam + 2x2 + orta şerit parçalara bölüp skorluyordu.
      Küçük insan çeyreğin içinde seyreliyor ve düşük skor alıyor → 67'nin 22'si "şüpheli"
      çıktı; bu YÖNTEMİN KENDİ KÖRLÜĞÜYDÜ, kanıt değil. Doğrulayıcı kutu üstünde eğitildi;
      tam kare ya da çeyrek verirsen dağılım dışına çıkarsın. Çeyrek kırpma TAŞINMADI.

    govde:
      "dogrulayici" (varsayılan) — sera.dogrulayici (DINOv2 ONNX + üretim kafası). Hızlı,
          torch gerektirmez. ⚠ ÖLÇÜM TOTOLOJİSİ: kafa bu karelerin çoğuyla eğitildi,
          BAĞIMSIZ DEĞİLDİR. Bağımsız hüküm için gün-dışla skor (kapsam_skorlari) veya
          govde="uc" kullanın.
      "uc" — dinov2 + clip + siglip2, her biri için etiketle eğitilmiş lojistik kafa,
          ortalama alınır. retro_denetim2.py'nin yaptığı budur; sayıları
          gate/retro_denetim2.json'da. torch + transformers + gate/gomu3.npz ister.

    kutu: "dedektor" (v2 davranışı — kareyi yeniden skorla) | "kayit" (olaydaki box).

    -> {"n","govde","sonuc","supheli_ts","ozet"}
       sonuc: [{"ts","cam","kaynak","det","skor","ort","not","p"}]
       ⚠ "kutu yok" çıkan kayıtlar da supheli_ts'e girer (retro_denetim2.py böyle yapıyordu).
    """
    import numpy as np
    import cv2

    from . import gorsel

    SAG = DENETIM_SAGLAM if esik_saglam is None else float(esik_saglam)
    SUP = DENETIM_SUPHELI if esik_supheli is None else float(esik_supheli)
    DE = ayar.DET_ESIK if det_esik is None else float(det_esik)
    MA = ayar.MIN_ALAN if min_alan is None else float(min_alan)

    kay = list(olaylar)
    if ornek and ornek < len(kay):
        rnd = random.Random(tohum)
        kay = sorted(rnd.sample(kay, ornek), key=lambda o: o["ts"])

    ded = _dedektor()
    if govde == "uc":
        # kırpma ÜZERİNDE çalışır (retro_denetim2.py:skor)
        _uc = _uc_govde_skorlayici()
        etiketler_ = ("dinov2", "clip", "siglip")

        def skorla(img_, box_, c_):
            return _uc(c_)
    else:
        # ⚠ kare+kutu ile çağrılır: kırpma sera.dogrulayici içinde yapılır, böylece
        #   ÜRETİMİN gördüğü aritmetiğin AYNISI çalışır (kırpmayı burada bir kez daha
        #   kırpmak PAD'i iki kez uygular ve skoru kaydırırdı).
        from . import dogrulayici as _dg
        dog = _dg.Dogrulayici(kafa_json=kafa_json)
        etiketler_ = ("dinov2",)

        def skorla(img_, box_, c_):
            s = dog.skor(img_, box_)
            return None if s is None else {"dinov2": float(s)}

    sonuc = []
    for i, o in enumerate(kay):
        p = o.get("p") or arsiv.mutlak(o.get("rel"), arsiv_)
        temel = {"ts": o["ts"], "cam": o["cam"], "kaynak": o.get("kaynak"), "p": p}
        img = cv2.imread(p) if p else None
        if img is None:
            sonuc.append({**temel, "det": None, "skor": None, "ort": None, "not": "kare okunamadi"})
            continue
        if kutu == "kayit" and o.get("box"):
            box, det = o["box"], o.get("det")
        else:
            t = ded.tara(img, esik=DE, min_alan=MA)
            ks = t["kutular"]
            box = ks[0]["kutu"] if ks else None
            det = ks[0]["skor"] if ks else 0.0
        if box is None:
            sonuc.append({**temel, "det": det, "skor": None, "ort": None, "not": "kutu yok"})
            continue
        c = gorsel.kirp(img, box)
        if c is None:
            sonuc.append({**temel, "det": det, "skor": None, "ort": None, "not": "kirpma yok"})
            continue
        r = skorla(img, box, c)
        if not r:
            sonuc.append({**temel, "det": det, "skor": None, "ort": None, "not": "skor yok"})
            continue
        sonuc.append({**temel, "det": round(float(det), 3) if det is not None else None,
                      "skor": r, "ort": float(np.mean(list(r.values()))), "box": box})
        if ilerleme and (i + 1) % ilerleme == 0 and not sessiz:
            print("  %d/%d" % (i + 1, len(kay)), flush=True)

    var = [s for s in sonuc if s.get("ort") is not None]
    kutusuz = [s for s in sonuc if s.get("not") == "kutu yok"]
    okunmaz = [s for s in sonuc if s.get("not") in ("kare okunamadi", "kirpma yok", "skor yok")]
    iyi = [s for s in var if s["ort"] >= SAG]
    orta = [s for s in var if SUP <= s["ort"] < SAG]
    kotu = [s for s in var if s["ort"] < SUP]
    ozet = {"skorlanan": len(var), "saglam": len(iyi), "sinirda": len(orta),
            "supheli": len(kotu), "kutusuz": len(kutusuz), "okunamadi": len(okunmaz),
            "esik_saglam": SAG, "esik_supheli": SUP, "govde": govde,
            "govdeler": list(etiketler_)}
    out = {"n": len(kay), "govde": govde, "sonuc": sonuc,
           "supheli_ts": [s["ts"] for s in kotu] + [s["ts"] for s in kutusuz],
           "ozet": ozet}
    if not sessiz:
        print("\nDENETIM (%s, KUTUYLA): skorlanan %d · kutu yok %d · okunamadi %d"
              % (govde, len(var), len(kutusuz), len(okunmaz)))
        print("  saglam  >=%.2f : %d" % (SAG, len(iyi)))
        print("  sinirda        : %d" % len(orta))
        print("  SUPHELI <%.2f  : %d" % (SUP, len(kotu)))
        print("  kaynak (supheli+kutusuz): %s"
              % dict(collections.Counter([s["kaynak"] for s in kotu] + [s["kaynak"] for s in kutusuz])))
        for s in sorted(kotu, key=lambda x: x["ort"])[:10]:
            print("   SUPHELI ort %.3f det %.2f  %s  %s"
                  % (s["ort"], s["det"] or 0, s["kaynak"], "/".join((s["p"] or "").split("/")[-2:])))
    if cikti:
        with open(cikti, "w") as f:
            json.dump(out, f, indent=1, default=float)
        print("YAZILDI", cikti)
    return out


def _uc_govde_skorlayici(gomu3=None, etiket_yolu=None, suphe_yolu=None):
    """dinov2 + clip + siglip2 → her biri için etiketle eğitilmiş lojistik kafa.
    BİREBİR retro_denetim2.py:basliklar + skor. torch/transformers/gomu3.npz ister."""
    import numpy as np
    import cv2
    import torch
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from transformers import AutoModel, AutoImageProcessor

    z = np.load(gomu3 or GOMU3, allow_pickle=True)
    fid = list(z["fid"])
    with open(etiket_yolu or ayar.ETIKET_763) as f:
        lab = json.load(f)
    sup = set()
    sp = suphe_yolu or ayar.ETIKET_DENETIM
    if os.path.exists(sp):
        with open(sp) as f:
            sup = {x["fid"] for x in json.load(f)["suphe"]}
    tut = [i for i, x in enumerate(fid) if x not in sup and lab.get(x, {}).get("v") in ("var", "yok")]
    y = np.array([1 if lab[fid[i]]["v"] == "var" else 0 for i in tut])
    H3 = {}
    for k in ("dinov2", "clip", "siglip"):
        F = z[k][tut]
        sc = StandardScaler().fit(F)
        H3[k] = (sc, LogisticRegression(C=ayar.C_LOJ, max_iter=ayar.MAX_ITER,
                                        class_weight=ayar.SINIF_AGIRLIK).fit(sc.transform(F), y))

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    md = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14", verbose=False).to(dev).eval()

    def yuk(a, C):
        try:
            return C.from_pretrained(a)
        except Exception:
            return C.from_pretrained(a, local_files_only=True)

    prc = yuk("openai/clip-vit-base-patch16", AutoImageProcessor)
    mc = yuk("openai/clip-vit-base-patch16", AutoModel).to(dev).eval()
    prs = yuk("google/siglip2-base-patch16-224", AutoImageProcessor)
    ms = yuk("google/siglip2-base-patch16-224", AutoModel).to(dev).eval()
    IMN = np.array(ayar.IMN, np.float32)
    IMS = np.array(ayar.IMS, np.float32)

    def skor(c):
        with torch.no_grad():
            b = (cv2.resize(c, (ayar.GIRIS, ayar.GIRIS))[:, :, ::-1].astype(np.float32) / 255.0 - IMN) / IMS
            t = torch.from_numpy(b.transpose(2, 0, 1)[None]).to(dev)
            Fd = md(t).float().cpu().numpy()
            im = [cv2.cvtColor(c, cv2.COLOR_BGR2RGB)]
            oc = getattr(mc, "vision_model", mc)(**prc(images=im, return_tensors="pt").to(dev))
            Fc = (oc.pooler_output if getattr(oc, "pooler_output", None) is not None
                  else oc.last_hidden_state.mean(1)).float().cpu().numpy()
            os_ = getattr(ms, "vision_model", ms)(**prs(images=im, return_tensors="pt").to(dev))
            Fs = (os_.pooler_output if getattr(os_, "pooler_output", None) is not None
                  else os_.last_hidden_state.mean(1)).float().cpu().numpy()
        r = {}
        for k, F in (("dinov2", Fd), ("clip", Fc), ("siglip", Fs)):
            sc, clf = H3[k]
            r[k] = float(clf.predict_proba(sc.transform(F))[0, 1])
        return r

    return skor


# ============================================================================ 7) ANİMASYON
def _animasyon(olay, cikti_dizin=None, min_kare=None, maks_kare=None, genis=None,
               sure_ms=None, kalite=None, metod=None, sadece_kaynak="dvr-hasat",
               arsiv_=None):
    """animasyon()'un ayrıntılı hâli -> {"yol","kare","kb","sebep"}. sebep=None ise üretildi."""
    from PIL import Image

    MINK = MIN_KARE if min_kare is None else int(min_kare)
    MAKS = MAKS_KARE if maks_kare is None else int(maks_kare)
    G = ANIM_GENIS if genis is None else int(genis)
    S = ANIM_SURE_MS if sure_ms is None else int(sure_ms)
    Q = ANIM_KALITE if kalite is None else int(kalite)
    M = ANIM_METOD if metod is None else int(metod)
    D = cikti_dizin or ANIM_DIZIN

    if sadece_kaynak and olay.get("kaynak") != sadece_kaynak:
        return {"yol": None, "kare": 0, "kb": 0, "sebep": "hasat-disi"}
    p0 = olay.get("p") or arsiv.mutlak(olay.get("rel"), arsiv_)
    kareler = arsiv.kardes_kareler(p0, arsiv_)
    if len(kareler) < MINK:
        return {"yol": None, "kare": len(kareler), "kb": 0, "sebep": "kare<%d" % MINK}
    if len(kareler) > MAKS:
        adim = len(kareler) / MAKS          # eşit aralık; başı-sonu korunur (retro_anim.py)
        kareler = [kareler[int(i * adim)] for i in range(MAKS)]
    ims = []
    for f in kareler:
        try:
            im = Image.open(f).convert("RGB")
        except Exception:
            continue
        ims.append(im.resize((G, int(im.height * G / im.width)), Image.LANCZOS))
    if len(ims) < MINK:
        return {"yol": None, "kare": len(ims), "kb": 0, "sebep": "okunamadi"}
    os.makedirs(D, exist_ok=True)
    hedef = os.path.join(D, "%d.webp" % int(olay["ts"]))
    ims[0].save(hedef, save_all=True, append_images=ims[1:], duration=S,
                loop=0, quality=Q, method=M)
    return {"yol": hedef, "kare": len(ims),
            "kb": round(os.path.getsize(hedef) / 1024), "sebep": None}


def animasyon(olay, **kw):
    """Bir retro olayın hareketli önizlemesi (animasyonlu WebP). 4G MALİYETİ SIFIR.

    BİREBİR retro_anim.py. DVR'dan yeni klip çekmek olay başına 2-6 MB demek ve kutunun
    paketi zaten aşılmış durumda. Ama ince hasat DERİN çekimlerde segment başına 63 kareye
    kadar indirmişti; o kareler diskte duruyor → animasyon onlardan kurulur, YENİ İNDİRME YOK.

    Parametreler: cikti_dizin · min_kare(5) · maks_kare(30) · genis(560) · sure_ms(200) ·
                  kalite(68) · metod(4) · sadece_kaynak("dvr-hasat") · arsiv_
    -> yazılan .webp yolu   ·   üretilemezse None (sebep için _animasyon() kullanın)
    """
    return _animasyon(olay, **kw)["yol"]


def animasyonlar(olaylar, cikti_dizin=None, rapor_yolu=None, sessiz=False, **kw):
    """animasyon()'u havuza uygula. BİREBİR retro_anim.py:main döngüsü + atlama sayacı.
    -> {"uretilen": [{"ts","kare","kb","cam","yol"}], "atlanan": {...}, "toplam_mb": ...}"""
    uretilen, atlanan = [], collections.Counter()
    for o in olaylar:
        r = _animasyon(o, cikti_dizin=cikti_dizin, **kw)
        if r["sebep"]:
            atlanan[r["sebep"]] += 1
            continue
        uretilen.append({"ts": int(o["ts"]), "kare": r["kare"], "kb": r["kb"],
                         "cam": o["cam"], "yol": r["yol"]})
        if not sessiz:
            print("  %s  %2d kare  %4.0f KB  kamera%s"
                  % (os.path.basename(r["yol"]), r["kare"], r["kb"], o["cam"]))
    out = {"uretilen": uretilen, "atlanan": dict(atlanan),
           "toplam_mb": round(sum(u["kb"] for u in uretilen) / 1024, 2)}
    if not sessiz:
        print("\nURETILEN: %d animasyon · toplam %.1f MB" % (len(uretilen), out["toplam_mb"]))
        print("atlanan:", out["atlanan"])
    if rapor_yolu:
        with open(rapor_yolu, "w") as f:
            json.dump(uretilen, f, indent=1)
        print("YAZILDI", rapor_yolu)
    return out


# ============================================================================ 8) KAPSAM
def kapsam_taramasi(izgara=None, kayitlar=None, canli=None, det_ates=None,
                    ust_sinirsiz=False, pencere_s=None, ziyaret_pencere_s=None,
                    retro_dahil=True, yaz=True):
    """Eşik ızgarasında kaç kare / kaç OLAY / kaçı YENİ.

    BİREBİR retro_kapsam.py 3. bölüm (IZGARA) + biliniyor()/ziyaret_biliniyor().
    Skorlar gate/retro_kapsam_skor.json'dan okunur — ÇIKARIM YENİDEN YAPILMAZ
    (gün-dışla kafalar orada eğitildi; aynı sayıyı iki kez üretmek denetlenebilirliği bozar).

    "YENİ" tanımı: uygulamada ZATEN görünen hiçbir şeyle örtüşmeyen olay. Örtüşme iki
    düzeyde ölçülür:
      · kamera düzeyi (±CANLI_PENCERE_S, aynı kamera)        -> "yeni"
      · ziyaret düzeyi (±ZIYARET_PENCERE_S, HERHANGİ kamera) -> "yeni_ziyaret"
    İkincisi daha katıdır: kişi 2 numaralı kamerada görülüp 5'te kaçırıldıysa bu YENİ BİR
    ZİYARET değildir, aynı ziyaretin ikinci kamerasıdır.

    ⚠⚠ retro_dahil — İKİ ESKİ SCRIPT BURADA FARKLI DAVRANIYOR, KARIŞTIRMA:
      True  (retro_kapsam.py) : referans = uygulamada GÖRÜNEN her şey, yani canlı olaylar
            + BUGÜNKÜ retro kayıtları. "Kaç YENİ kazanırız" sorusunun doğru referansı budur;
            yoksa zaten takvimde duran 67 retro kaydı tekrar "kazanç" diye sayılır.
      False (retro_build2.py) : referans = SADECE gerçek canlı yakalamalar. Orada soru
            farklıdır — "bu anı sistem o an gördü mü?"; retro havuzuyla çakışma ayrı bir
            bayrakla (v1_ortusen) ölçülür.
      İkisi karıştırılınca `yeni` sayısı 2-3 katına şişer (ölçüldü: det.05/dog.80 noktasında
      12 yerine 28). Varsayılan retro_kapsam.py semantiğidir çünkü bu fonksiyonun sorusu odur.

    izgara : [(det, dog), ...] veya {"det": [...], "dog": [...]} (kartezyen)
    -> {"izgara": [...], "det_ates":, "n_kayit":, "canli_olay":, "retro_dahil":}
    """
    DA = DET_ATES if det_ates is None else float(det_ates)
    P = CANLI_PENCERE_S if pencere_s is None else int(pencere_s)
    Z = ZIYARET_PENCERE_S if ziyaret_pencere_s is None else int(ziyaret_pencere_s)

    if izgara is None:
        izgara = {"det": [0.05, 0.10, 0.15, 0.20, 0.25, 0.35],
                  "dog": [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]}
    if isinstance(izgara, dict):
        noktalar = [(d, v) for d in izgara["det"] for v in izgara["dog"]]
    else:
        noktalar = [tuple(x) for x in izgara]

    K = kapsam_skorlari() if kayitlar is None else kayitlar
    C = canli_kayitlar(retro_haric=not retro_dahil) if canli is None else canli
    tab = zaman_tablosu(C)
    tum_ts = sorted(int(e["ts"]) for e in C if e.get("ts"))

    def ziyaret_biliniyor(ts):
        i = bisect.bisect_left(tum_ts, int(ts))
        for j in (i - 1, i):
            if 0 <= j < len(tum_ts) and abs(tum_ts[j] - int(ts)) <= Z * 1000:
                return True
        return False

    out = []
    if yaz:
        print("%-6s %-6s | %6s %6s %6s %6s %6s | %6s %6s" %
              ("det>=", "dog>=", "kare", "olay", "canli", "YENI", "yeniZ", "diagK", "diagO"))
    for dt, vt in noktalar:
        sec = [r for r in K
               if (r.get("det") or 0) >= dt and (r.get("dog_oof") or 0) >= vt
               and (ust_sinirsiz or (r.get("det") or 0) < DA)]
        ol = arsiv.olaylastir(sec)
        nb = sum(1 for o in ol if yakin(tab, o["cam"], o["ts"], P))
        nz = sum(1 for o in ol if not ziyaret_biliniyor(o["ts"]))
        dk = sum(1 for r in sec if str(r.get("kaynak", "")).startswith("diag"))
        do = sum(1 for o in ol if (o.get("p") or "").find("/diag_") >= 0)
        satir = {"det": dt, "dog": vt, "kare": len(sec), "olay": len(ol),
                 "canli_ortusen": nb, "yeni": len(ol) - nb, "yeni_ziyaret": nz,
                 "diag_kare": dk, "diag_olay": do}
        out.append(satir)
        if yaz:
            print("%-6.2f %-6.2f | %6d %6d %6d %6d %6d | %6d %6d" %
                  (dt, vt, len(sec), len(ol), nb, len(ol) - nb, nz, dk, do))
    return {"izgara": out, "det_ates": DA, "n_kayit": len(K), "canli_olay": len(C),
            "ust_sinirsiz": bool(ust_sinirsiz), "retro_dahil": bool(retro_dahil),
            "pencere_s": P, "ziyaret_pencere_s": Z}


def oneri(yol=None, yaz=True):
    """Eşik ÖNERİSİNİ ölçülmüş rapordan OKU — yeniden ölçme.

    Kaynak sırası: gate/retro_events2.json meta (kuralın uygulanmış hâli) →
    gate/retro_kapsam.json:onerilen_kural (ölçüm ayrıntısı).
    Hiçbiri yoksa ayar.py'deki sabitlere düşer ve `kaynak: "ayar"` yazar.
    """
    d = {"dog_esik": DOG_ESIK_KADEMELI, "det_guclu": DET_GUCLU,
         "uzlasma_gerek": UZLASMA_GEREK, "kaynak": "ayar", "tanim": None, "olculen": None}
    if os.path.exists(RETRO_V2):
        with open(RETRO_V2) as f:
            v2 = json.load(f)
        d.update({"dog_esik": v2.get("dog_esik", d["dog_esik"]),
                  "det_guclu": v2.get("det_guclu", d["det_guclu"]),
                  "uzlasma_gerek": v2.get("uzlasma_gerek", d["uzlasma_gerek"]),
                  "tanim": v2.get("kural"), "kaynak": RETRO_V2,
                  "olay": len(v2.get("olaylar", [])),
                  "yeni_olay": sum(1 for o in v2.get("olaylar", []) if o.get("yeni"))})
    if os.path.exists(KAPSAM):
        with open(KAPSAM) as f:
            kp = json.load(f)
        ok = kp.get("onerilen_kural") or {}
        d["olculen"] = {k: v for k, v in ok.items() if k != "ornek"}
        d["taban"] = kp.get("taban")
        d["uzlasma_etiketli"] = kp.get("uzlasma_etiketli")
        d["kapsam_kaynak"] = KAPSAM
    if yaz:
        print("ONERILEN KURAL: %s" % d.get("tanim"))
        print("  kaynak: %s" % d["kaynak"])
        if d.get("olculen"):
            o = d["olculen"]
            print("  olculen: %d kare -> %d olay · uygulamada olmayan %d (ziyaret duzeyinde %d)"
                  % (o.get("kare", 0), o.get("olay", 0), o.get("yeni_olay", 0),
                     o.get("yeni_ziyaret", 0)))
            r = o.get("etiketli_RETRO_BOLGESI") or {}
            t = (d.get("taban") or {}).get("gun_disla_DURUST") or {}
            print("  ESLESTIRILMIS NOKTA (ikisi de gun-disla, ikisi de det<%.2f bolgesi):" % DET_ATES)
            print("     TABAN     TP %s · FP %s" % (t.get("tp"), t.get("fp")))
            print("     BU KURAL  TP %s · FP %s" % (r.get("tp"), r.get("fp")))
    return d


# ============================================================================ 9) TAVAN
def tavan(pencere_s=None, ev_now=None, denetim=None, hacim=None, arsiv_=None,
          cikti=None, yaz=True):
    """RETRO'NUN TAVANI — eşikten BAĞIMSIZ yapısal sınırlar. BİREBİR retro_tavan.py.

    Eşik taraması (kapsam_taramasi) "kaç kare daha geçer"i söyler. Bu ondan ÖNCEKİ soru:
    retro havuzu ilkece ne kadar büyüyebilir? Üç ölçüm:

      1. TABAN HATA — canlı sistemin BUGÜNKÜ yanlış oranı (gate/labels.json olay denetimi).
         "Hata oranı artmasın" cümlesinin sayısal karşılığı budur; retro buna göre
         kıyaslanır, SIFIRA göre değil. Sıfıra kıyaslamak ölçüm totolojisidir.
      2. ÖRNEKLEME TAVANI — timeline 5 dakikada bir kare. Bilinen canlı ziyaretlerin
         içine hiç timeline karesi düşmeyenini HİÇBİR EŞİK kurtaramaz; retro'nun tavanı budur.
      3. GERÇEK OLAYDA YAKALAMA — denetimden TP çıkmış canlı olayın timeline karşılığında
         det/dog ne veriyor? Doğrusu doğrulayıcıdan değil, İNSAN DENETİMİNDEN gelir —
         bu yüzden bu üçüncü ölçüm bağımsızdır.

    ⚠ hacim kutuları gate/hacim_kuru.json'dan okunur; orada olmayan kare için det/dog 0.0
      sayılır (retro_tavan.py böyle yapıyordu — "kutu yok" ile "skor 0" burada aynı kovada).

    -> {"taban_hata","ornekleme_tavani","ziyaret_sure_s","gercekte_yakalama","detay_kesit"}
    """
    import statistics

    AR = arsiv_ or ARSIV
    P = TAVAN_PENCERE_S if pencere_s is None else int(pencere_s)
    rap = {}

    per = canli_kayitlar(ev_now, retro_haric=False, cam_gerek=False)
    ziy = canli_ziyaretler(ev_now)
    lab = olay_denetimi(denetim)

    # ------------------------------------------------------------ 1) TABAN HATA
    say = collections.Counter(lab.values())
    canli_id = {e["id"]: e for e in per if e.get("id")}
    kesisim = {k: v for k, v in lab.items() if k in canli_id}
    retro_lab = {k: v for k, v in kesisim.items() if canli_id[k].get("retro")}
    live_lab = {k: v for k, v in kesisim.items() if not canli_id[k].get("retro")}
    sus_lab = {k: v for k, v in kesisim.items() if canli_id[k].get("suspect")}

    def oran(d):
        t = sum(1 for v in d.values() if v == "TP")
        f = sum(1 for v in d.values() if v == "FP")
        return {"n": len(d), "TP": t, "FP": f, "yanlis_oran": f / max(1, t + f)}

    rap["taban_hata"] = {"tum_denetim": {"say": dict(say), **oran(lab)},
                         "olay_id_eslesen": oran(kesisim),
                         "CANLI_olaylar": oran(live_lab),
                         "RETRO_olaylar": oran(retro_lab),
                         "SUSPECT_olaylar": oran(sus_lab)}
    if yaz:
        print("=" * 74)
        print("1) TABAN HATA — Alperen'in denetledigi olaylar")
        print("=" * 74)
        for k, v in rap["taban_hata"].items():
            print("  %-18s n=%-4d TP=%-4d FP=%-4d  yanlis %%%.0f"
                  % (k, v["n"], v["TP"], v["FP"], 100 * v["yanlis_oran"]))

    # ------------------------------------------------- 2) ÖRNEKLEME TAVANI
    tl = collections.defaultdict(list)
    for p in glob.glob(os.path.join(AR, "timeline", "*", "*", "*.jpg")):
        c, t = arsiv.cam_of(p), ts_timeline(p)
        if c and t:
            tl[int(c)].append((int(t), p))
    for c in tl:
        tl[c].sort()
    tl_ts = {c: [t for t, _ in v] for c, v in tl.items()}

    def en_yakin(cam, ts):
        a = tl_ts.get(int(cam))
        if not a:
            return None, None
        i = bisect.bisect_left(a, int(ts))
        en, ep = None, None
        for j in (i - 1, i):
            if 0 <= j < len(a):
                d = abs(a[j] - int(ts))
                if en is None or d < en:
                    en, ep = d, tl[int(cam)][j][1]
        return en, ep

    canli_per = [e for e in per if not e.get("retro") and e.get("cam")]
    kap = collections.Counter()
    detay = []
    for e in canli_per:
        d, p = en_yakin(e["cam"], e["ts"])
        ic = d is not None and d <= P * 1000
        kap["kapsanan" if ic else "timeline-DISI"] += 1
        detay.append({"id": e.get("id"), "cam": e["cam"], "ts": e["ts"],
                      "mesafe_s": None if d is None else int(d / 1000),
                      "kare": p if ic else None})
    rap["ornekleme_tavani"] = {"canli_olay": len(canli_per), "pencere_s": P, **dict(kap),
                               "kapsama_orani": kap["kapsanan"] / max(1, len(canli_per))}
    if yaz:
        print("\n" + "=" * 74)
        print("2) ORNEKLEME TAVANI — 5 dk'lik timeline canli olaylarin kacini goruyor?")
        print("=" * 74)
        print("  canli (retro olmayan) insan olayi: %d" % len(canli_per))
        print("  +-%d sn'de timeline karesi olan   : %d  (%%%.0f)"
              % (P, kap["kapsanan"], 100 * rap["ornekleme_tavani"]["kapsama_orani"]))
        print("  hicbir karesi olmayan             : %d  <- HICBIR ESIK bunlari kurtaramaz"
              % kap["timeline-DISI"])

    sur = sorted((z.get("dur", 0) or 0) / 1000 for z in ziy)
    if sur:
        rap["ziyaret_sure_s"] = {"n": len(sur), "medyan": statistics.median(sur),
                                 "ort": sum(sur) / len(sur),
                                 "kisa_300s_alti": sum(1 for s in sur if s < 300),
                                 "sifir": sum(1 for s in sur if s == 0)}
        if yaz:
            print("  ziyaret suresi: medyan %.0f sn · <300 sn olan %d/%d"
                  % (statistics.median(sur), rap["ziyaret_sure_s"]["kisa_300s_alti"], len(sur)))

    # ------------------------------------------- 3) GERÇEK OLAYDA YAKALAMA
    HK = {}
    for f in (hacim or (HACIM_KURU,)):
        if os.path.exists(f):
            with open(f) as fh:
                HK.update({r["p"]: r for r in json.load(fh)["kayit"]})
    sat = []
    for e, d in zip(canli_per, detay):
        if not d["kare"]:
            continue
        r = HK.get(d["kare"])
        sat.append({"id": e.get("id"), "cam": e["cam"], "mesafe_s": d["mesafe_s"],
                    "det": (r or {}).get("det", 0.0), "dog": (r or {}).get("dog", 0.0),
                    "kutu": bool(r), "denetim": live_lab.get(e.get("id"))})
    dn_tp = [s for s in sat if s["denetim"] == "TP"]
    dn_fp = [s for s in sat if s["denetim"] == "FP"]
    rap["gercekte_yakalama"] = {"eslesen_kare": len(sat), "denetimli_TP": len(dn_tp),
                                "denetimli_FP": len(dn_fp)}
    if yaz:
        print("\n" + "=" * 74)
        print("3) DENETIMDEN TP CIKMIS CANLI OLAYIN TIMELINE KARESI NE DIYOR?")
        print("=" * 74)
        print("  timeline karesi eslesen canli olay: %d (denetimli TP %d · FP %d)"
              % (len(sat), len(dn_tp), len(dn_fp)))
    tab = []
    for dt in TAVAN_DET_IZGARA:
        for vt in TAVAN_DOG_IZGARA:
            a = sum(1 for s in dn_tp if s["det"] >= dt and s["dog"] >= vt)
            b = sum(1 for s in dn_fp if s["det"] >= dt and s["dog"] >= vt)
            tab.append({"det": dt, "dog": vt, "tp": a, "fp": b,
                        "tp_oran": a / max(1, len(dn_tp)), "fp_oran": b / max(1, len(dn_fp))})
            if yaz:
                print("  det>=%.2f dog>=%.2f -> gercek TP'nin %2d/%2d'i (%%%.0f) · "
                      "gercek FP'nin %2d/%2d'i (%%%.0f)"
                      % (dt, vt, a, len(dn_tp), 100 * a / max(1, len(dn_tp)),
                         b, len(dn_fp), 100 * b / max(1, len(dn_fp))))
    rap["gercekte_yakalama"]["izgara"] = tab
    rap["detay_kesit"] = sat[:200]

    if cikti:
        with open(cikti, "w") as f:
            json.dump(rap, f, indent=1, default=float)
        print("\nYAZILDI", cikti)
    return rap


# ============================================================================ 10) PANO
def _pano_kovasi(kova, n, tohum, anahtar, arsiv_=None):
    """Kontakt sayfası için kayıt kümesi seç -> (kayitlar, baslik, evren, orneklendi)."""
    AR = arsiv_ or ARSIV
    if kova in ("v1", "yeni", "v2"):
        # kaynak: retro_pano2.py — havuz kovaları, rastgele örneklem, tohumlu
        if kova == "v1":
            kay = oku(RETRO_V1)
            bas = "KIYAS TABANI — MEVCUT v1 RETRO HAVUZU"
        else:
            kay = oku(RETRO_V2)
            if kova == "yeni":
                kay = [o for o in kay if o.get("yeni")]
                bas = "v2'NIN YENI GETIRDIKLERI"
            else:
                bas = "v2 RETRO HAVUZU (tamami)"
        evren = len(kay)
        if n and n < len(kay):
            rnd = random.Random(tohum)
            kay = rnd.sample(kay, n)
        kay = sorted(kay, key=lambda o: o["ts"])
        for o in kay:
            if not o.get("p") and o.get("rel"):
                o["p"] = os.path.join(AR, o["rel"])
        return kay, "%s (rastgele %d/%d)" % (bas, len(kay), evren), evren, True

    # kaynak: retro_pano.py — kapsam raporunun ÖRNEK kovaları, ilk N, örnekleme yok
    with open(KAPSAM) as f:
        rap = json.load(f)
    if kova == "kural":
        og = (rap.get("onerilen_kural") or {}).get("ornek") or []
        bas = "ONERILEN KURALIN YENI GETIRDIKLERI — %s" % (rap.get("onerilen_kural") or {}).get("tanim")
    elif kova == "ariza":
        og = (rap.get("hat_arizasi") or {}).get("ornek") or []
        bas = "HAT-ARIZASI: det>=%.2f arsiv karesi ama uygulamada olay YOK" % DET_ATES
    else:
        og = ((rap.get("adaylar") or {}).get(anahtar) or {}).get("ornek") or []
        bas = "YENI ADAY — %s" % anahtar
    evren = len(og)
    kay = [dict(o, p=os.path.join(AR, o["p"])) for o in og[:n]] if n else \
          [dict(o, p=os.path.join(AR, o["p"])) for o in og]
    return kay, "%s (%d/%d)" % (bas, len(kay), evren), evren, False


def pano(kova="yeni", n=None, tohum=20260802, mod=None, cikti=None, baslik=None,
         anahtar="+HAT-ARIZASI det0.05_dog0.70", kutu_bul=True, kutular=None,
         sutun=None, arsiv_=None, meta_yaz=True):
    """RETRO ADAYLARINI TEK GÖRSELDE GÖSTER — kontakt sayfası. 30 saniyede "liste temiz mi".

    BİREBİR retro_pano.py + retro_pano2.py (çizim işi sera.gorsel'e devredildi; geometri
    ve hücre boyutları ayar.HUCRE_ONAYAR'da aynı sayılarla duruyor).

    kova:
      "yeni" (varsayılan) — v2'nin YENİ getirdikleri · "v1" KIYAS TABANI (aynı gözle) ·
      "v2"  tüm v2 havuzu   → üçü de retro_pano2.py: mod "pano" (300x340/5 sütun),
                              rastgele N örneklem, TOHUMLU (tekrarlanabilir).
      "kural" · "ariza" · <anahtar>  → retro_kapsam.json'un ÖRNEK kovaları, retro_pano.py:
                              mod "kucuk" (200x240/8 sütun), ilk N, örnekleme YOK.

    ⚠ KIYAS TABANI OLMADAN BAKMA: "yeni"nin yanlış oranı tek başına anlamsızdır. Aynı
      gözle "v1" panosuna da bakılır; karar iki panonun FARKINA göre verilir. retro_pano2.py
      "v1" kovasını tam bu yüzden içeriyor.

    kutu_bul=True → kaydın kutusu hacim dosyalarında yoksa üretim dedektörüyle çıkarılır
      (retro_pano2.py:kutu_bul; esik 0.03 · min_alan 0.0018 · kutu KIRPILMAZ → sinirla=False).

    -> yazılan .jpg yolu (yanına aynı adla .json meta: hücre no -> kayıt)
    """
    from . import gorsel

    AR = arsiv_ or ARSIV
    havuz_kovasi = kova in ("v1", "yeni", "v2")
    M = mod or ("pano" if havuz_kovasi else "kucuk")
    N = n if n is not None else (PANO_N if havuz_kovasi else PANO_N_KAPSAM)

    kay, oto_baslik, evren, _ = _pano_kovasi(kova, N, tohum, anahtar, AR)
    if not kay:
        print("pano: kova bos ->", kova)
        return None
    KUT = hacim_kutulari() if kutular is None else kutular
    ded = _dedektor() if kutu_bul else None

    hucreler, meta = [], []
    for i, o in enumerate(kay, 1):
        p = o.get("p") or arsiv.mutlak(o.get("rel"), AR)
        box = o.get("box") or KUT.get(p)
        if not box and ded is not None and p:
            b = ded.en_iyi(p, sinirla=False)
            box = b["kutu"] if b else None
        z = o.get("zaman") or arsiv.yerel_zaman(o["ts"], "%m-%d %H:%M")
        dt = o.get("det")
        dg = o.get("dog_oof") if o.get("dog_oof") is not None else o.get("dog")
        ust = ["#%02d  k%s  %s" % (i, o.get("cam", "?"), z[-11:]),
               "det %s  dogOOF %s" % ("%.2f" % dt if dt is not None else "-",
                                      "%.2f" % dg if dg is not None else "-")]
        hucreler.append(gorsel.hucre(p, box, ust, mod=M))
        meta.append({"no": i, "rel": arsiv.rel(p, AR), "cam": o.get("cam"), "ts": o.get("ts"),
                     "zaman": z, "det": dt, "dog_oof": dg, "kaynak": o.get("kaynak")})

    out = cikti or ayar.gate("pano_v2_%s.jpg" % kova if havuz_kovasi else "pano_%s.jpg" % kova)
    # sütun sayısı MODA bağlı: "pano" 5 (retro_pano2.py) · "kucuk" 8 (retro_pano.py).
    # ayar.SUTUN'a düşmek retro_pano.py'nin 8'lik ızgarasını 5'e daraltırdı.
    S = sutun or ayar.HUCRE_ONAYAR.get(M, {}).get("sutun")
    y = gorsel.kontakt(hucreler, out, sutun=S, baslik=baslik or oto_baslik)
    if y and meta_yaz:
        mj = y[:-4] + ".json"
        with open(mj, "w") as f:
            json.dump({"seed": tohum, "kova": kova, "mod": M, "evren": evren,
                       "ornek": meta}, f, indent=1, default=float)
        print("meta:", mj)
    return y


def pano_zoom(secim, cikti=None, kat=None, kutular=None, arsiv_=None, baslik=None):
    """BELİRSİZ HÜCRELERİ BÜYÜT — kontakt sayfasında karar veremediğin hücreler.
    BİREBİR retro_zoom.py (mod="zoom": yw=bw*1.25+6, yh=bh*1.25+6).

    ⚠ NEDEN VAR: "0 yanlış" demeden önce belirsizleri ÇÖZEBİLDİĞİNİ göstermek şart.
      Kararsız hücreyi görmezden gelip sayıya katmamak ölçümü kendi lehine bozar.

    secim: "yeni:10,12,19" tek dize · ["yeni:10,12", "v1:1,14"] liste ·
           {"yeni": [10,12], "v1": [1,14]} sözlük   (numaralar pano() meta json'undan)
    -> yazılan .jpg yolu
    """
    from . import gorsel

    AR = arsiv_ or ARSIV
    if isinstance(secim, str):
        secim = [secim]
    if isinstance(secim, dict):
        cift = list(secim.items())
    else:
        cift = []
        for a in secim:
            k, v = a.split(":")
            cift.append((k, [int(x) for x in v.split(",") if x.strip()]))

    KUT = hacim_kutulari() if kutular is None else kutular
    hucreler = []
    for kova, nolar in cift:
        mj = ayar.gate("pano_v2_%s.json" % kova)
        if not os.path.exists(mj):
            mj = ayar.gate("pano_%s.json" % kova)
        with open(mj) as f:
            ix = {m["no"]: m for m in json.load(f)["ornek"]}
        for no in nolar:
            m = ix.get(int(no))
            if not m:
                print("pano_zoom: %s#%s meta'da yok, atlandi" % (kova, no))
                continue
            p = arsiv.mutlak(m["rel"], AR)
            ust = ["%s#%02d k%s %s" % (kova.upper(), m["no"], m.get("cam"), m.get("zaman", "")),
                   "det %s dogOOF %s"
                   % ("%.2f" % m["det"] if m.get("det") is not None else "-",
                      "%.2f" % m["dog_oof"] if m.get("dog_oof") is not None else "-")]
            hucreler.append(gorsel.hucre(p, KUT.get(p), ust, mod="zoom", kat=kat,
                                         interp=_LANCZOS))
    return gorsel.kontakt(hucreler, cikti or ayar.gate("pano_v2_zoom.jpg"),
                          baslik=baslik or "BELIRSIZ HUCRELER — YAKIN KIRPIM", kalite=94)


# ============================================================================ 11) ÇIKTI
def temizle(olaylar, arsiv_=None, v1_alani=True):
    """Havuzu dosyaya yazılabilir hâle getir: sure_s hesapla, rel ekle, ts_son/uyeler at.

    BİREBİR retro_build.py/retro_build2.py çıktı hazırlığı.
    `rel` ŞART: istemci ASLA mutlak yol görmez, sunucu kayıttan okur
    (etiketleme uçlarındaki path-traversal dersinin aynısı).
    """
    for o in olaylar:
        if "ts_son" in o:
            o["sure_s"] = int((o["ts_son"] - o["ts"]) / 1000)
            o.pop("ts_son", None)
        o.pop("uyeler", None)
        if o.get("p"):
            o["rel"] = arsiv.rel(o["p"], arsiv_)
        if v1_alani and "v1_ortusen" in o:
            o["yeni"] = not o["v1_ortusen"]
    return olaylar


def dosyaya_yaz(olaylar, yol, uretim="sera.retro", **meta):
    """Havuzu retro_import.py'nin beklediği şemayla yaz.

    Şema: {"olaylar": [...], "uretim": ..., "birlestir_s": ..., + verilen meta}
    Olay alanları: ts · cam · n · det · dog · [dog_oof] · kaynak · p · rel · sure_s
    """
    ol = temizle(list(olaylar))
    gov = {"olaylar": ol, "uretim": uretim, "birlestir_s": BIRLESTIR_S}
    gov.update(meta)
    d = os.path.dirname(os.path.abspath(yol))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(yol, "w") as f:
        json.dump(gov, f, indent=1, default=float)
    print("YAZILDI %s  (%d olay)" % (yol, len(ol)))
    return yol


def oku(yol):
    """Diskteki bir retro havuzunu oku -> olay listesi."""
    with open(yol) as f:
        d = json.load(f)
    return d["olaylar"] if isinstance(d, dict) else d


def karsilastir(a, b, ad_a="a", ad_b="b", yaz=True):
    """İki havuzu KIYASLA: olay sayısı, kamera dağılımı, gün dağılımı, (cam,ts) kümesi farkı.

    Doğrulamanın aracı: refactor sonrası "mantık kaymış mı" sorusunun tek cevabı.
    -> {"ayni": bool, ...}
    """
    def kim(o):
        return (int(o["cam"]), int(o["ts"]))

    def gun(o):
        return arsiv.yerel_zaman(o["ts"], "%Y-%m-%d")

    A, B = {kim(o) for o in a}, {kim(o) for o in b}
    kamA = dict(sorted(collections.Counter(int(o["cam"]) for o in a).items()))
    kamB = dict(sorted(collections.Counter(int(o["cam"]) for o in b).items()))
    gunA = dict(sorted(collections.Counter(gun(o) for o in a).items()))
    gunB = dict(sorted(collections.Counter(gun(o) for o in b).items()))
    r = {"n_%s" % ad_a: len(a), "n_%s" % ad_b: len(b),
         "kamera_%s" % ad_a: kamA, "kamera_%s" % ad_b: kamB,
         "gun_%s" % ad_a: gunA, "gun_%s" % ad_b: gunB,
         "sadece_%s" % ad_a: sorted(A - B), "sadece_%s" % ad_b: sorted(B - A),
         "ortak": len(A & B),
         "ayni": (len(a) == len(b) and A == B and kamA == kamB and gunA == gunB)}
    if yaz:
        print("=" * 74)
        print("KIYAS  %s  vs  %s" % (ad_a, ad_b))
        print("=" * 74)
        print("  olay sayisi   : %-6d %-6d %s" % (len(a), len(b), "AYNI" if len(a) == len(b) else "FARKLI"))
        print("  kamera %-6s : %s" % (ad_a, kamA))
        print("  kamera %-6s : %s   %s" % (ad_b, kamB, "AYNI" if kamA == kamB else "FARKLI"))
        print("  (cam,ts) ortak: %d · sadece %s: %d · sadece %s: %d"
              % (len(A & B), ad_a, len(A - B), ad_b, len(B - A)))
        print("  gun dagilimi  : %s" % ("AYNI" if gunA == gunB else "FARKLI"))
        if gunA != gunB:
            for g in sorted(set(gunA) | set(gunB)):
                if gunA.get(g, 0) != gunB.get(g, 0):
                    print("     %s  %s=%d  %s=%d" % (g, ad_a, gunA.get(g, 0), ad_b, gunB.get(g, 0)))
        for k, S in (("sadece_" + ad_a, A - B), ("sadece_" + ad_b, B - A)):
            for c, t in sorted(S)[:10]:
                print("     %-12s kamera%d  %s" % (k, c, arsiv.yerel_zaman(t)))
        print("  >>> %s" % ("MANTIK KORUNDU (birebir ayni)" if r["ayni"] else "FARK VAR — incele"))
    return r


# ============================================================================ 10) PRESETLER
def v1_havuzu(dog_esik=None, birlestir_s=None, en_iyi=True, arsiv_=None, sessiz=False):
    """MEVCUT (uygulamada canlı) retro havuzunu yeniden üret — retro_build.py'nin aynısı.

    Kaynak kovaları: full_scan A (vskor>=0.80) + DVR hasadı (koşulsuz).
    Zaman parser'ı v1'in EKSİK olanı (ts_timeline); tekleştirme temsilcisi canlı `dog` skoru;
    temsilci alanlarından SADECE `p` taşınır. Üçü de v1 davranışı.

    -> (olaylar, rapor)
    """
    DE = DOG_ESIK_RETRO if dog_esik is None else float(dog_esik)
    P = BIRLESTIR_S if birlestir_s is None else int(birlestir_s)
    ham = adaylar(None, DE, kaynaklar=("full_scan", "hasat"), v1_zaman=True,
                  arsiv_=arsiv_, sessiz=sessiz)
    ol = teklestir(ham, pencere_s=P, skor_alani="dog", tasi=("p",))
    if en_iyi:
        en_iyi_kareler(ol, dedektor=None, arsiv_=arsiv_, sessiz=sessiz)
    temizle(ol, arsiv_, v1_alani=False)
    # v1 çıktısında box/dog_oof/uzlasma alanları YOKTU — şemayı birebir tut
    for o in ol:
        for k in ("box", "dog_oof", "uzlasma"):
            o.pop(k, None)
    rapor = {"kural": "vskor>=%.2f (full_scan A) + DVR hasadi KOSULSUZ" % DE,
             "dog_esik": DE, "birlestir_s": P, "olay": len(ol),
             "kamera": dict(sorted(collections.Counter(o["cam"] for o in ol).items())),
             "kaynak": dict(collections.Counter(o["kaynak"] for o in ol))}
    if not sessiz:
        print("teklestirilmis OLAY: %d" % len(ol))
        print("  kamera: %s" % rapor["kamera"])
        print("  kaynak: %s" % rapor["kaynak"])
    return ol, rapor


def v2_havuzu(dog_esik=None, det_guclu=None, uzlasma_gerek=None, birlestir_s=None,
              en_iyi=True, canli=None, v1=None, etiket_surum="763", arsiv_=None,
              sessiz=False):
    """GENİŞLETİLMİŞ retro havuzu — retro_build2.py'nin aynısı.

    v1'e göre dört değişiklik, dördü de ÖLÇÜMDEN geliyor (gate/retro_kapsam.json):
      1. zaman parser'ı düzeltildi (arsiv.ts_of) — v1'in sessizce çöpe attığı kayıtlar geri geldi
      2. det<0.52 ÜST SINIRI kaldırıldı — "dedektör ateşleme eşiğini geçmiş ama uygulamada
         olay yok" kovası (hat arızası) artık dahil
      3. sabit eşik yerine KADEMELİ kural (kural_kademeli)
      4. daha önce hiç taranmamış diag_vps + diag_hd eklendi

    Ayrıca v1'de HİÇ OLMAYAN çakışma kontrolü uygulanır: canlı olayla ±6 dk örtüşen kayıt
    retro DEĞİLDİR, elenir. (v1 havuzunun 13/67'si bu kontrolden kalırdı.)

    etiket_surum: "763" → v2'nin gördüğü anlık görüntü (sayıyı yeniden üretmek için).
                  "946" → ASIL etiket seti (bugünkü doğru hüküm; daha çok segment eleyebilir).

    -> (havuz, rapor)   ·   havuz = canlıyla çakışmayan + etiketle elenmemiş olaylar
    """
    DE = DOG_ESIK_KADEMELI if dog_esik is None else float(dog_esik)
    DG = DET_GUCLU if det_guclu is None else float(det_guclu)
    UZ = UZLASMA_GEREK if uzlasma_gerek is None else int(uzlasma_gerek)
    P = BIRLESTIR_S if birlestir_s is None else int(birlestir_s)

    def _k(r):
        return kural_kademeli(r, DE, DG, UZ)

    ham = adaylar(None, None, kaynaklar=("skor", "hasat"), kural=_k,
                  arsiv_=arsiv_, sessiz=sessiz)
    if not sessiz:
        ha = sum(1 for r in ham if r["det"] is not None and r["det"] >= DET_ATES)
        print("   kural: dog_oof>=%.2f VE (det>=%.2f VEYA %d/3 uzlasma) · det UST SINIRI YOK"
              % (DE, DG, UZ))
        print("   bunlarin %d'i det>=%.2f (v1'in HIC almadigi hat-arizasi bandi)" % (ha, DET_ATES))

    ol = teklestir(ham, pencere_s=P, skor_alani="dog_oof")
    if en_iyi:
        en_iyi_kareler(ol, dedektor=None, arsiv_=arsiv_, sessiz=sessiz)
    if not sessiz:
        print("TEKLESTIRME (%d dk): %d olay" % (P // 60, len(ol)))

    C = canli_kayitlar() if canli is None else canli
    V1 = (oku(RETRO_V1) if os.path.exists(RETRO_V1) else []) if v1 is None else v1
    havuz = canli_cakisma(ol, C, pencere_s=CANLI_PENCERE_S)
    elenen = [o for o in ol if o.get("canli_ortusen")]
    havuz_cakisma(havuz, V1, pencere_s=V1_PENCERE_S)
    yeni = [o for o in havuz if not o["v1_ortusen"]]
    v1_kirli = 0
    if V1:
        tabC = zaman_tablosu(C)
        v1_kirli = sum(1 for o in V1 if yakin(tabC, int(o["cam"]), int(o["ts"]), CANLI_PENCERE_S))
    if not sessiz:
        print("CAKISMA: canli olayla ortusen -> ELENDI %d · v1 havuzuyla ayni %d · YENI %d"
              % (len(elenen), len(havuz) - len(yeni), len(yeni)))
        print("   (denetim: v1 havuzunun %d/%d kaydi canli olayla cakisiyormus — v1 bu kontrolu"
              " hic yapmiyordu)" % (v1_kirli, len(V1)))

    ET = etiket_yollari(etiket_surum)
    kesisim = {"v1_havuzu": etiket_kesinligi(V1, ET) if V1 else None,
               "v2_havuzu_ATMADAN_ONCE": etiket_kesinligi(havuz, ET),
               "v2_YENI": etiket_kesinligi(yeni, ET)}
    havuz, atilan = etiketle_ele(havuz, etiket=ET, arsiv_=arsiv_, sessiz=sessiz)
    kalan_ts = {(o["cam"], o["ts"]) for o in havuz}
    yeni = [o for o in yeni if (o["cam"], o["ts"]) in kalan_ts]

    temizle(havuz, arsiv_)
    rapor = {"kural": "dog_oof>=%.2f VE (det>=%.2f VEYA %d/3 uzlasma); det ust siniri YOK"
                      % (DE, DG, UZ),
             "dog_esik": DE, "det_guclu": DG, "uzlasma_gerek": UZ, "birlestir_s": P,
             "skor_kaynagi": "dog_oof = GUN-DISLA (day-holdout); karar bununla verildi",
             "kullanilmayan_sinyal": ["arka-plan referansi/NCC (olculdu: veto ZARARLI)",
                                      "zamansal tutarlilik/hareket (olculdu: katki yok)"],
             "olay": len(havuz), "yeni_olay": len(yeni),
             "kamera": dict(sorted(collections.Counter(o["cam"] for o in havuz).items())),
             "kaynak": dict(collections.Counter(o["kaynak"] for o in havuz)),
             "etiket_kesisimi": kesisim, "etiketle_atilan_hasat": atilan,
             "elenen_canli_ortusen": [{"ts": o["ts"], "cam": o["cam"],
                                       "rel": arsiv.rel(o.get("p") or "")} for o in elenen],
             "v1_canli_ile_cakisan": v1_kirli, "etiket_surum": etiket_surum}
    return havuz, rapor


# ============================================================================ envanter
def ozet(yaz=True):
    """Diskteki retro havuzlarının envanteri — "elimizde ne var" tek satır."""
    d = {}
    for ad, y in (("v1", RETRO_V1), ("v2", RETRO_V2)):
        if not os.path.exists(y):
            d[ad] = None
            continue
        ol = oku(y)
        d[ad] = {"yol": y, "olay": len(ol),
                 "kamera": dict(sorted(collections.Counter(int(o["cam"]) for o in ol).items())),
                 "kaynak": dict(collections.Counter(o.get("kaynak") for o in ol)),
                 "gun": len({arsiv.yerel_zaman(o["ts"], "%Y-%m-%d") for o in ol}),
                 "yeni": sum(1 for o in ol if o.get("yeni"))}
    d["hasat_kare"] = len(glob.glob(os.path.join(HASAT_DIZIN, "*.jpg")))
    d["animasyon"] = len(glob.glob(os.path.join(ANIM_DIZIN, "*.webp")))
    d["kapsam_skor_kayit"] = (len(kapsam_skorlari()) if os.path.exists(KAPSAM_SKOR) else 0)
    try:
        c = canli_kayitlar(retro_haric=False)
        d["canli_person_olay"] = len(c)
        d["canli_retro_isaretli"] = sum(1 for e in c if e.get("retro"))
    except Exception as e:
        d["canli_person_olay"] = "okunamadi: %s" % str(e)[:60]
    if yaz:
        print("=== sera.retro envanteri ===")
        for k, v in d.items():
            print("  %-22s %s" % (k, v))
    return d


# ============================================================================ CLI
def _alan_farki(eski, yeni):
    """Ortak olaylarda alan alan kıyas -> (sayaclar, temsilci_kare_farklari)."""
    ix = {(int(o["cam"]), int(o["ts"])): o for o in eski}
    s = collections.Counter()
    fark_p = []
    for o in yeni:
        e = ix.get((int(o["cam"]), int(o["ts"])))
        if not e:
            continue
        if (e.get("rel") or "") != (o.get("rel") or ""):
            s["temsilci_kare"] += 1
            fark_p.append({"ts": int(o["ts"]), "cam": int(o["cam"]),
                           "disk": e.get("rel"), "sera": o.get("rel")})
        if (e.get("dog") or 0) != (o.get("dog") or 0):
            s["dog"] += 1
        if (e.get("det") or 0) != (o.get("det") or 0):
            s["det"] += 1
        if e.get("n") != o.get("n"):
            s["n"] += 1
    return s, fark_p


def _dogrula(sessiz=False, cikti=None):
    """v1 havuzunu YENİDEN ÜRET ve gate/retro_events.json ile kıyasla.
    'Çalışıyor' demenin bedeli budur: sayı tutmuyorsa mantık kaymıştır.

    İKİ AŞAMA — çünkü diskteki dosyanın kendisinde bilinen bir kusur var:
      A. en_iyi=False → retro_build.py'nin GERÇEKTE yaptığı iş. Diskteki dosya buradan
         çıktı; her alan birebir tutmalı (temsilci kare dahil).
      B. en_iyi=True  → pre-roll düzeltmesi de uygulanmış hâl. Burada temsilci kare
         diskten FARKLI çıkar; fark gate/temsilci_duzelt.json'un "yeni" değerleriyle
         birebir örtüşmelidir. Örtüşüyorsa bu kayma değil, ölçülmüş DÜZELTMEdir.

    ⚠ Diskteki retro_events.json neden kusurlu: retro_build.py'deki en_iyi_kare() hiç
      çalışmadı — sistem python3'ünde cv2 yok, ImportError `except Exception` tarafından
      yutuldu, iş sessizce atlandı. DVR hasadından gelen kayıtların temsilcisi hâlâ
      segmentin `_001`'i, yani PRE-ROLL karesi. temsilci_duzelt.py bunu ölçüp düzeltmişti.
    """
    print("=" * 74)
    print("DOGRULAMA — sera.retro ile v1 havuzunu yeniden uret, diskteki ile kiyasla")
    print("=" * 74)
    eski = oku(RETRO_V1)

    print("\n--- A) en_iyi=False (retro_build.py'nin GERCEKTE yaptigi is) ---")
    hamv, _ = v1_havuzu(en_iyi=False, sessiz=sessiz)
    kA = karsilastir(eski, hamv, "disk", "sera.retro", yaz=not sessiz)
    sA, farkA = _alan_farki(eski, hamv)
    print("  ALAN KIYASI (ortak %d): temsilci %d · dog %d · det %d · uye %d"
          % (kA["ortak"], sA["temsilci_kare"], sA["dog"], sA["det"], sA["n"]))
    A_tam = kA["ayni"] and not sA
    print("  >>> A: %s" % ("TAM OZDES — mantik korundu." if A_tam else "FARK VAR"))

    print("\n--- B) en_iyi=True (pre-roll duzeltmesi de uygulanmis) ---")
    yeni, _ = v1_havuzu(en_iyi=True, sessiz=sessiz)
    kB = karsilastir(eski, yeni, "disk", "sera.retro", yaz=not sessiz)
    sB, farkB = _alan_farki(eski, yeni)
    print("  ALAN KIYASI (ortak %d): temsilci %d · dog %d · det %d · uye %d"
          % (kB["ortak"], sB["temsilci_kare"], sB["dog"], sB["det"], sB["n"]))

    # temsilci farkı = ÖLÇÜLMÜŞ pre-roll düzeltmesi mi?
    # İKİ dosya: temsilci_duzelt.json (27'lik bozuk.json girdisinden 17 düzeltme) +
    # temsilci_duzelt_ek.json (o girdide HİÇ olmayan 1 Ağustos'un 3 segmenti; aynı
    # scriptle ayrıca ölçüldü). Eksik olan sera.retro değil, o günkü girdi listesiydi.
    duz = {}
    for dyol in (ayar.gate("temsilci_duzelt.json"), ayar.gate("temsilci_duzelt_ek.json")):
        if os.path.exists(dyol):
            with open(dyol) as f:
                duz.update(json.load(f))
    ort = sapan = kapsam_disi = 0
    for r in farkB:
        d = duz.get(str(r["ts"]))
        if d is None:
            kapsam_disi += 1
        elif d.get("yeni") == r["sera"] and d.get("eski") == r["disk"]:
            ort += 1
        else:
            sapan += 1
            print("     SAPAN ts=%d  disk=%s  sera=%s  duzelt.yeni=%s"
                  % (r["ts"], r["disk"], r["sera"], d.get("yeni")))
    print("  TEMSILCI FARKI temsilci_duzelt.json ile: ortusen %d · sapan %d · kayitsiz %d"
          % (ort, sapan, kapsam_disi))
    B_tam = (kB["ayni"] and sB["dog"] == 0 and sB["det"] == 0 and sB["n"] == 0
             and sapan == 0 and kapsam_disi == 0)
    print("  >>> B: %s" % ("olay/skor birebir; temsilci farklarinin TAMAMI olculmus "
                           "pre-roll duzeltmesi." if B_tam else "ACIKLANAMAYAN FARK VAR"))

    tam = A_tam and B_tam
    print("\n" + "=" * 74)
    print(">>> SONUC: %s" % ("MANTIK KORUNDU." if tam else "MANTIK KAYMIS — dokume bak."))
    print("=" * 74)
    out = {"A_ham": {"kiyas": kA, "alan_farki": dict(sA), "tam": A_tam},
           "B_en_iyi": {"kiyas": kB, "alan_farki": dict(sB), "temsilci_fark": farkB,
                        "duzelt_ortusen": ort, "duzelt_sapan": sapan,
                        "duzelt_kayitsiz": kapsam_disi, "tam": B_tam},
           "tam_ozdes": tam}
    if cikti:
        with open(cikti, "w") as f:
            json.dump(out, f, indent=1, default=float)
        print("YAZILDI", cikti)
    return out


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]

    def _arg(bayrak, vars_):
        return a[a.index(bayrak) + 1] if bayrak in a and a.index(bayrak) + 1 < len(a) else vars_

    if "--dogrula" in a:
        r = _dogrula(cikti=_arg("--yaz", None))
        sys.exit(0 if r["tam_ozdes"] else 1)
    elif "--oneri" in a:
        oneri()
    elif "--kapsam" in a:
        kapsam_taramasi()
    elif "--tavan" in a:
        tavan(cikti=TAVAN_JSON)
    elif "--pano" in a:
        pano(_arg("--pano", "yeni"), n=int(_arg("--n", 0)) or None,
             tohum=int(_arg("--tohum", 20260802)))
    elif "--zoom" in a:
        pano_zoom(a[a.index("--zoom") + 1:])
    else:
        ozet()

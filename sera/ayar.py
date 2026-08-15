# -*- coding: utf-8 -*-
"""
sera.ayar — TÜM yollar, eşikler ve sabitler TEK yerde (2 Ağu 2026).

NEDEN: 64 script'in her birinde `AR = "/mnt/data/sera-arsiv"`, `MIN_AREA = 0.0018`,
`W, H, PAD, GIRIS = 96, 192, 0.25, 224` satırları kopyalanmıştı. Bir eşiği değiştirmek
6 dosyayı elle düzeltmek demekti; biri unutulunca ölçüm sessizce kayıyordu.

KURAL — buradaki hiçbir sayı KAFADAN yazılmadı. Her satırın yanında hangi dosyadan
geldiği yazar. Bu bir refactor: değer değiştirmek bu dosyanın işi DEĞİL.

ORTAM DEĞİŞKENİ: her sabit `SERA_<AD>` ile ezilebilir.
    SERA_ARSIV=/mnt/yedek/sera-arsiv  SERA_DOG_ESIK=0.70  python sera_cli.py ...
Tip, varsayılanın tipinden çıkarılır (int/float/bool/str).

Kullanım:
    from sera import ayar
    ayar.MIN_ALAN            # 0.0018
    ayar.yol("gate", "oof_esik.json")
    ayar.ozet()              # çözülmüş ayarları yazdır
    ayar.dogrula()           # dosyalar gerçekten var mı
"""
import os

# ============================================================================ ortam
_EK = "SERA_"


def _oku(ad, vars):
    """SERA_<ad> varsa onu, yoksa varsayılanı döndür. Tip varsayılandan çıkarılır."""
    o = os.environ.get(_EK + ad)
    if o is None:
        return vars
    if isinstance(vars, bool):
        return o.strip().lower() in ("1", "true", "yes", "evet", "on")
    if isinstance(vars, int) and not isinstance(vars, bool):
        return int(o)
    if isinstance(vars, float):
        return float(o)
    return o


# ============================================================================ yollar
# kaynak: full_scan.py:AR · oof_sweep.py:KOK · hacim_kuru.py:AR · retro_build.py:AR (7+ dosyada aynı)
ARSIV = _oku("ARSIV", "/mnt/data/sera-arsiv")
# kaynak: full_scan.py:OUT · retro_kapsam.py:GATE · retro_pano.py:GATE
GATE = _oku("GATE", os.path.join(ARSIV, "gate"))

# kaynak: retro_kapsam.py:KOD (person-detect kökü) · sera_pipeline.py:KOD
KOD = _oku("KOD", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# kaynak: olay_denetim2.py:KOK  (proje kökü: vps/ + deploy/ + person-detect/ burada)
KOK = _oku("KOK", os.path.dirname(KOD))
# kaynak: full_scan.py / retro_build.py — ONNX'ler vps/ altında duruyor
VPS_KOD = _oku("VPS_KOD", os.path.join(KOK, "vps"))
# kaynak: train_verifier3.py:MODEL — weights/ dizini
AGIRLIK = _oku("AGIRLIK", os.path.join(KOD, "weights"))
# kaynak: eski scriptlerin taşınacağı yer (sera_cli.py tasarımı)
ESKI = _oku("ESKI", os.path.join(KOD, "eski"))

# kaynak: oof_sweep.py:SCR · train_verifier3.py:SCR · gece_sweep.py:SCR (aynı sabit 10+ dosyada)
SCRATCH = _oku("SCRATCH", "/tmp/claude-1000/-home-schrodiger/"
                          "c40afbf8-4e1f-48c7-93c6-5d1e9873bc1a/scratchpad")

# ============================================================================ modeller
# kaynak: full_scan.py — üretim dedektörü, sınıf 0 = person
YOLO640 = _oku("YOLO640", os.path.join(VPS_KOD, "yolo11s.onnx"))
YOLO960 = _oku("YOLO960", os.path.join(VPS_KOD, "yolo11s_960.onnx"))
# kaynak: train_verifier3.py:MODEL · olay_denetim2.py:GOVDE — doğrulayıcı gövdesi (346 MB)
DINOV2 = _oku("DINOV2", os.path.join(AGIRLIK, "verifier_dinov2.onnx"))
# kaynak: full_scan.py:HEAD — ÜRETİMDEKİ kafa (v2, varyant "cok HARIC")
KAFA = _oku("KAFA", os.path.join(AGIRLIK, "verifier_head.json"))
# kaynak: train_verifier3.py:HEAD_YENI — 946 etiketle eğitilmiş, HENÜZ DAĞITILMADI
KAFA_V3 = _oku("KAFA_V3", os.path.join(AGIRLIK, "verifier_head_v3.json"))

# ============================================================================ etiket / veri
# ⚠ ASIL ETİKET SETİ 1113'lük (3 Ağu 00:30, Alperen 167 kare daha etiketledi).
#   Aktif-öğrenmeyle seçilen 100 karenin 80'i + kuyrukta bekleyen 87 kare işlendi.
#   Kamera dağılımı düzeldi: k2 19 -> 49 · k1 72 -> 119 · k3 113 -> 146 (k2 en aç kameraydı).
#   Retro havuzunun ÖLÇÜLEMEZ zayıf kolundan 4 kare etiketlendi -> o kol artık ölçülebilir.
# kaynak: VPS /opt/sera/labels.json (3 Ağu çekimi)
ETIKET = _oku("ETIKET", os.path.join(SCRATCH, "labels_1113.json"))
KUYRUK = _oku("KUYRUK", os.path.join(SCRATCH, "label_queue_1113.json"))
# kaynak: train_verifier3.py:LAB_YENI / Q_YENI — "946 ne biliyordu" kıyası için durur
ETIKET_946 = _oku("ETIKET_946", os.path.join(SCRATCH, "labels_946.json"))
KUYRUK_946 = _oku("KUYRUK_946", os.path.join(SCRATCH, "label_queue_946.json"))
# kaynak: train_verifier3.py:LAB_ESKI · oof_sweep.py (763'lük anlık görüntü)
ETIKET_763 = _oku("ETIKET_763", os.path.join(SCRATCH, "labels.json"))
KUYRUK_763 = _oku("KUYRUK_763", os.path.join(SCRATCH, "label_queue.json"))
# ⚠ BU ETİKET SETİ DEĞİL: 119 kayıtlık TP/FP DOĞRULAYICI DENETİM dosyası.
# kaynak: olay_denetim2.py:kalibre() — eşik kalibrasyonunda kullanılır
DENETIM = _oku("DENETIM", os.path.join(GATE, "labels.json"))
# kaynak: train_verifier3.py — eğitimden çıkarılan şüpheli etiketler
ETIKET_DENETIM = _oku("ETIKET_DENETIM", os.path.join(GATE, "etiket_denetim.json"))

# gömü önbellekleri — kaynak: oof_sweep.py:EMB (763) · train_verifier3.py:EMB_YENI (946)
GOMU_763 = _oku("GOMU_763", os.path.join(GATE, "oof_gomu.npz"))
GOMU_946 = _oku("GOMU_946", os.path.join(GATE, "oof_gomu_946.npz"))

# ============================================================================ VPS
# kaynak: proje notları + deploy/ · doğrulayıcı kafası orada /opt/sera/models/verifier_head.json
VPS_HOST = _oku("VPS_HOST", "")   # SERA_VPS_HOST ile verilir
VPS_ANAHTAR = _oku("VPS_ANAHTAR", os.path.expanduser("~/.ssh/id_ed25519"))
VPS_KOK = _oku("VPS_KOK", "/opt/sera")
VPS_ONEK = VPS_KOK.rstrip("/") + "/"          # yol çevirisinde kullanılan önek
# kaynak: /opt/sera/verifier.py bunu bir kez yükler → değişiklik için servis restart ŞART
VPS_KAFA = _oku("VPS_KAFA", VPS_KOK + "/models/verifier_head.json")
# kaynak: vps/state_service.py:LABEL_FILE / LABEL_QUEUE (sera/etiket.py senkronu buradan çeker)
VPS_ETIKET = _oku("VPS_ETIKET", VPS_KOK.rstrip("/") + "/labels.json")
VPS_KUYRUK = _oku("VPS_KUYRUK", VPS_KOK.rstrip("/") + "/label_queue.json")
VPS_SERVISLER = ("sera-person", "sera-person-canary", "sera-state")

# ============================================================================ dedektör
# kaynak: vps/person_watch_v3.py:31 — 16 Tem CANLI ölçüm (gölgede oturan aile üyeleri
#         kamera3'te conf 0.41 ama alan 0.0025 → eski 0.005 eşiği GERÇEK insanları yutuyordu)
MIN_ALAN = float(_oku("MIN_ALAN", 0.0018))
# kaynak: full_scan.py:DET_ATES · retro_kapsam.py:DET_ATES — üretimin ateşleme eşiği
DET_ATES = float(_oku("DET_ATES", 0.52))
# kaynak: hacim_kuru.py / retro_build2.py — taramada kutu ÜRETME eşiği (ateşleme değil)
DET_TARA = float(_oku("DET_TARA", 0.05))
# kaynak: full_scan.py:DET_TARA — full_scan aynı işi 0.10 ile yapmıştı; sayıları
#         yeniden üretmek isteyen o dosyayı bununla çağırsın (mantık korundu)
DET_TARA_FULLSCAN = float(_oku("DET_TARA_FULLSCAN", 0.10))
# kaynak: olay_denetim2.py:kutular(esik=0.03) · retro_build.py:skor() · retro_pano2.py
#         — ham çıktı süzme tabanı; karar eşiği DEĞİL
DET_ESIK = float(_oku("DET_ESIK", 0.03))

# kaynak: full_scan.py:onnx() — max(h,w) >= 700 ise HD sayılır ve 960 modeli kullanılır
HD_KENAR = int(_oku("HD_KENAR", 700))
BOYUT_640 = int(_oku("BOYUT_640", 640))
BOYUT_960 = int(_oku("BOYUT_960", 960))
DOLGU = int(_oku("DOLGU", 114))                     # letterbox gri — full_scan.py:onnx()
PERSON_SINIF = int(_oku("PERSON_SINIF", 0))         # COCO sınıf 0 = person
IPLIK = int(_oku("IPLIK", os.cpu_count() or 4))     # oof_sweep.py:so.intra_op_num_threads

# ============================================================================ doğrulayıcı
# kaynak: oof_sweep.py:34 · train_verifier3.py:47 · hacim_kuru.py:31 · olay_denetim2.py:46
#         (kırpma mantığı 6 dosyada BİREBİR aynıydı)
PAD = float(_oku("PAD", 0.25))          # kutu çevresine bağlam payı (zemin bilgisi ayrımda işe yarıyor)
KIRP_W = int(_oku("KIRP_W", 96))        # insan kırpması dikey — sabit oran, letterbox
KIRP_H = int(_oku("KIRP_H", 192))
GIRIS = int(_oku("GIRIS", 224))         # DINOv2 patch 14 → 224 = 16x16 patch
IMN = (0.485, 0.456, 0.406)             # ImageNet ortalama — train_verifier.py:gomu()
IMS = (0.229, 0.224, 0.225)             # ImageNet std
# kaynak: weights/verifier_head.json:len(coef) — dinov2_vitb14 gömü boyutu
GOMU_BOYUT = int(_oku("GOMU_BOYUT", 768))
# kaynak: train_verifier3.py:gomuler() — gövde ağır, yarım çekirdek yeter (dedektörle yarışmasın)
DOG_IPLIK = int(_oku("DOG_IPLIK", max(2, (os.cpu_count() or 4) // 2)))
# kaynak: ASIL etiket seti 946'lık — sera.etiket varsayılan sürümü
ETIKET_SURUM = _oku("ETIKET_SURUM", "1113")   # 3 Ağu: 167 yeni etiket geldi

# kaynak: weights/verifier_head.json:esik_guvenli · train_verifier3.py — CANLI çalışma noktası.
# ⚠ BU SAYI CANLININ AYNASIDIR, ÖNERİ DEĞİL. Canlı 0.50 iken burası 0.50 kalır; yoksa ölçüm
#   canlıyla uyuşmaz. Canlı değişince İKİSİ BİRDEN güncellenir.
# ⚠ 2 Ağu ÖLÇÜLDÜ (gate/esik_sertifika.json, olay düzeyi, LOEO, 61 gerçek + 56 yanlış olay):
#   0.50 SERTİFİKALANAMIYOR ve DOMİNE. (a) α=%5/δ=%5 için 153 etiketli gerçek-ziyaret OLAYI
#   gerekir, bugün 61 var; bugünkü n ile 0.50'nin sertifikalandığı en küçük α = %12.2.
#   (b) [0.454985, 0.50) aralığında HİÇ yanlış yok → 0.50 aynı 52 yanlışı keser ama 2 yerine
#   3 gerçek ziyaret kaçırır. Etkin sınır = pozitif skorların SIRA İSTATİSTİKLERİ; aradaki
#   yuvarlak sayılar (0.30 / 0.35 / 0.50 / 0.85) her zaman domine.
DOG_ESIK = float(_oku("DOG_ESIK", 0.50))
# Neyman-Pearson sertifikalı ateşleme eşiği (α=%5, δ=%5, k=1). HENÜZ DAĞITILMADI.
# Ölçülen: 21/56 saha yanlışı kesilir, 61 gerçek ziyaretin 0'ı kaçar. Denemek için:
#   SERA_DOG_ESIK=0.015 python3 sera_cli.py olc
# Tam sıra istatistiği 0.015071690655875854 — AŞAĞI yuvarlandı; yukarı (0.0151) yuvarlamak
# o gerçek ziyareti KESER (bkz. sera/olay.py "EŞİK YUVARLANMAZ").
DOG_ESIK_SERTIFIKA = float(_oku("DOG_ESIK_SERTIFIKA", 0.015))
ESIK_SERTIFIKA_JSON = _oku("ESIK_SERTIFIKA_JSON", os.path.join(GATE, "esik_sertifika.json"))
# kaynak: weights/verifier_head.json:esik_agresif
DOG_ESIK_AGRESIF = float(_oku("DOG_ESIK_AGRESIF", 0.85))
# kaynak: retro_build.py:DOG_ESIK — geçmişe yazarken temkinli ol
DOG_ESIK_RETRO = float(_oku("DOG_ESIK_RETRO", 0.80))
# kaynak: retro_build2.py:DOG_ESIK / DET_GUCLU / UZLASMA_GEREK — ÖLÇÜLEN kademeli kural
DOG_ESIK_KADEMELI = float(_oku("DOG_ESIK_KADEMELI", 0.70))
DET_GUCLU = float(_oku("DET_GUCLU", 0.20))
UZLASMA_GEREK = int(_oku("UZLASMA_GEREK", 2))

# ⚠ "YANLIŞ" EŞİĞİ KAFADAN ATILMAZ — sera.olcum/oof_esik.py fold-dışı skorlardan TÜRETİR.
# Aşağıdaki sayı 2 Ağu koşusunun sonucudur (gate/oof_esik.json), taze türetme yoksa yedek.
# Gerçek insan kaybı %1.1 (2/181), yakalanan yanlış %26 (148/...). "Makul görünen" 0.10 gibi
# bir eşik gerçek tespitleri SİLERDİ: gerçek insanların %5'i 0.2637'nin ALTINDA.
YANLIS_ESIK_YEDEK = float(_oku("YANLIS_ESIK_YEDEK", 0.003874243935570121))
OOF_ESIK_JSON = _oku("OOF_ESIK_JSON", os.path.join(GATE, "oof_esik.json"))

# lojistik kafa hiperparametreleri — kaynak: train_verifier.py / oof_sweep.py / train_verifier3.py
C_LOJ = float(_oku("C_LOJ", 0.05))
MAX_ITER = int(_oku("MAX_ITER", 2000))
SINIF_AGIRLIK = _oku("SINIF_AGIRLIK", "balanced")
KFOLD = int(_oku("KFOLD", 5))

# ============================================================================ zaman / olay
TZ_SAAT = int(_oku("TZ_SAAT", 3))                  # Europe/Istanbul = UTC+03
# kaynak: retro_build.py:BIRLESTIR_S · retro_build2.py · retro_kapsam.py — 6 dk = tek olay
BIRLESTIR_S = int(_oku("BIRLESTIR_S", 360))
CANLI_PENCERE_S = int(_oku("CANLI_PENCERE_S", 360))    # retro_build2.py — canlı olayla çakışma
V1_PENCERE_S = int(_oku("V1_PENCERE_S", 360))          # retro_build2.py — v1 havuzuyla çakışma
ZIYARET_PENCERE_S = int(_oku("ZIYARET_PENCERE_S", 600))  # retro_kapsam.py — aynı ziyaret

# kaynak: gece_sweep.py:gece() — ÖLÇÜM tanımı (20:00-06:00)
GECE_BAS = int(_oku("GECE_BAS", 20))
GECE_BIT = int(_oku("GECE_BIT", 6))
# kaynak: vps/person_watch_v3.py:is_night() — ÜRETİM tanımı (21:00-07:00 TR).
# ⚠ İkisi FARKLI. Ölçümde gece_sweep tanımı kullanıldı; üretim kapıları 21-07 ile çalışıyor.
GECE_BAS_URETIM = int(_oku("GECE_BAS_URETIM", 21))
GECE_BIT_URETIM = int(_oku("GECE_BIT_URETIM", 7))

# kaynak: vps/person_watch_v3.py:POLL_S — pre-roll karesi ~1 poll öncesi
POLL_S = float(_oku("POLL_S", 20.0))

# ============================================================================ üretim kapıları
# SALT REFERANS — vps/person_watch_v3.py'nin canlı eşikleri. Buradan DEĞİŞTİRİLMEZ,
# canlı dosyaya dokunulmaz; ölçüm/rapor "üretim bugün ne yapıyor" derken buraya bakar.
URETIM = {
    "CONF": 0.35,            # person_watch_v3.py:30 — 19 Tem eval: 0 FP + recall .29
    "MIN_AREA": 0.0018,      # :31
    "NIGHT_CONF": 0.55,      # :64  ⚠ NIGHT_CONF v3'te NO-OP (gece sub-yolu nadir, HD yetkili)
    "NIGHT_MIN_AREA": 0.004,  # :65
    "HD_CONF": 0.40,         # :73
    "NIGHT_HD_CONF": 0.52,   # :74
    "HD_MIN_AREA": 0.0006,   # :76 — HD karede uzak kişi alan~0.0012
    "IMG_SZ_HD": 960,        # :197
}

# ⚠⚠ BİLİNEN AÇIK — sera.olay ve SISTEM.md'ye yazılacak:
#   vps/person_watch_v3.py:  `if do_fire and _verifier is not None and det_box:`
#   Şüpheli kapıları (hd-red / tekrar-statik / cok-olcek) ateşi kestiğinde DOĞRULAYICI HİÇ
#   ÇALIŞMIYOR — AUC 0.98'lik model tam gerektiği yerde devre dışı. Ölçüldü: doğrulayıcı
#   >=0.50 ile ateşlenseydi 16 GERÇEK insan kurtulur, 0 yanlış geçerdi (OOF ve olay-dışla
#   LOEO, iki bağımsız skorlama aynı sonucu veriyor). En zararlı kapı tekrar-statik: 7'nin
#   6'sı gerçek insan.
#   ⚠ SAYI: bu not bir ara turda "14" yazıyordu; genişletilmiş havuzda yeniden ölçüldü,
#     16 oldu. Kaynak tek: sera.olay.kapi_bulgusu() → bastirilmis_gercek / kurtarilabilir.
#     Elle güncelleme yapma, `sera_cli.py durum` her koşuda tazesini basar.
SUPHELI_KAPILAR = ("hd-red", "tekrar-statik", "cok-olcek", "dogrulayici")

# ============================================================================ kontakt sayfası
# kaynak: retro_pano2.py:HUC_W/HUC_H/SUTUN/UST — en zengin varyant, varsayılan bu
HUC_W = int(_oku("HUC_W", 300))
HUC_H = int(_oku("HUC_H", 340))
SUTUN = int(_oku("SUTUN", 5))
UST_BANT = int(_oku("UST_BANT", 34))            # hücre içi etiket şeridi yüksekliği
BASLIK_BANT = int(_oku("BASLIK_BANT", 34))      # panonun tepesindeki başlık şeridi
JPEG_KALITE = int(_oku("JPEG_KALITE", 92))      # retro_pano2.py 92 · retro_pano.py 88

# hücre ön ayarları — üç eski script'in geometrisi birebir korunur
HUCRE_ONAYAR = {
    "pano": {"w": 300, "h": 340, "ust": 34, "kat": 1.9, "sutun": 5},    # retro_pano2.py
    "kucuk": {"w": 200, "h": 240, "ust": 26, "kat": 1.9, "sutun": 8},   # retro_pano.py
    "zoom": {"w": 360, "h": 400, "ust": 34, "kat": 1.25, "sutun": 5},   # retro_zoom.py
    "kare": {"w": 260, "h": 260, "ust": 34, "kat": 1.1, "sutun": 7},    # olay_pano.py
}

# ============================================================================ yardımcı
def yol(*parca):
    """Arşiv köküne göre yol kur: yol('gate', 'oof_esik.json')."""
    return os.path.join(ARSIV, *parca)


def gate(*parca):
    """gate/ dizinine göre yol kur."""
    return os.path.join(GATE, *parca)


def yanlis_esik(varsayilan=None):
    """'Yanlış tespit' eşiği. ÖNCE gate/oof_esik.json'dan (taze türetilmiş) okunur;
    yoksa YANLIS_ESIK_YEDEK. Kaynak: oof_esik.py — kafadan sayı yazma yasağının uygulaması."""
    import json
    try:
        with open(OOF_ESIK_JSON) as f:
            return float(json.load(f)["yanlis_esik"])
    except Exception:
        return float(YANLIS_ESIK_YEDEK if varsayilan is None else varsayilan)


def kafa_yolu(v3=False):
    """Doğrulayıcı kafası. v3=True → 946 etiketli yeni kafa (varsa), yoksa üretim kafası.
    Kaynak: olay_denetim2.py'nin KAFA seçim mantığı."""
    if v3 and os.path.exists(KAFA_V3):
        return KAFA_V3
    return KAFA


_SAYILABILIR = ("ARSIV", "GATE", "KOD", "KOK", "VPS_KOD", "AGIRLIK", "ESKI", "SCRATCH",
                "YOLO640", "YOLO960", "DINOV2", "KAFA", "KAFA_V3",
                "ETIKET", "KUYRUK", "ETIKET_763", "KUYRUK_763", "DENETIM",
                "MIN_ALAN", "DET_ATES", "DET_TARA", "DET_ESIK", "HD_KENAR",
                "BOYUT_640", "BOYUT_960", "DOLGU", "PERSON_SINIF", "IPLIK",
                "PAD", "KIRP_W", "KIRP_H", "GIRIS", "DOG_ESIK", "DOG_ESIK_SERTIFIKA",
                "ESIK_SERTIFIKA_JSON", "DOG_ESIK_AGRESIF",
                "DOG_ESIK_RETRO", "DOG_ESIK_KADEMELI", "DET_GUCLU", "UZLASMA_GEREK",
                "C_LOJ", "KFOLD", "TZ_SAAT", "BIRLESTIR_S", "GECE_BAS", "GECE_BIT",
                "HUC_W", "HUC_H", "SUTUN")

# hangi dosyaların GERÇEKTEN var olması gerektiği (dogrula() bunlara bakar)
_ZORUNLU = ("ARSIV", "GATE", "KOD", "VPS_KOD", "AGIRLIK",
            "YOLO640", "YOLO960", "DINOV2", "KAFA")


def ozet(yaz=True):
    """Çözülmüş ayarları döndür (ve istenirse yazdır). Rapora/loga koymak için."""
    d = {k: globals()[k] for k in _SAYILABILIR}
    if yaz:
        print("=== sera.ayar (SERA_<AD> ile ezilebilir) ===")
        for k in _SAYILABILIR:
            ez = " [SERA_%s]" % k if os.environ.get(_EK + k) else ""
            print("  %-18s %s%s" % (k, d[k], ez))
    return d


def dogrula(yaz=True):
    """Zorunlu yol/dosyalar gerçekten var mı? {ad: (yol, var_mi)} döndürür.
    'Çalışmayana çalışıyor deme' kuralının ayar katmanındaki karşılığı."""
    r = {}
    for k in _ZORUNLU:
        p = globals()[k]
        r[k] = (p, os.path.exists(p))
    if yaz:
        for k, (p, v) in r.items():
            print("  %s %-10s %s" % ("OK  " if v else "YOK ", k, p))
    return r


if __name__ == "__main__":
    ozet()
    print()
    dogrula()

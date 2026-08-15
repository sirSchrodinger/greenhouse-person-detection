# -*- coding: utf-8 -*-
"""sera.etiket — etiket + kuyruk okuma, VPS senkronu, kayıt birleştirme, dağılım.

NEDEN BU DOSYA VAR
------------------
Etiket bu projedeki EN PAHALI kaynak (elle kaydırılarak toplanıyor). Buna rağmen
"etiketi oku, kuyrukla eşleştir, kutuyu seç, yolu çevir, elenecekleri ele" bloğu
14 ayrı dosyada kopyalanmıştı ve hepsi aynı değildi:

  kaynak dosya                 etiket seti      kutu kaynağı            şüpheli eleme
  ---------------------------  ---------------  ----------------------  -------------
  train_verifier3.py (ASIL)    labels_946       pbox or kutu            VAR (3 fid)
  train_verifier2.py           labels (763)     pbox or kutu            VAR
  oof_esik.py                  labels_946       (gömü npz'den)          yok
  etiket_denetim.py            labels (763)     pbox or kutu            yok
  oof_sweep.py / esik_sweep.py labels (763)     pbox or kutu            yok
  kuyruk_sirala.py, k5_analiz.py, gece_sweep.py, govde_yaris.py, retro_*.py … hepsi ayrı

Devralınan mantık — birlestir_kayitlar() gövdesi train_verifier3.py:main()'in
kayıt döngüsünden HARFİ HARFİNE alındı:
  · kutu       = it["pbox"] or it["kutu"]      → ÜRETİM kutusu (YOLO-World "ywbox" DEĞİL)
  · yol        = it["p"].replace("/opt/sera/", ARSIV + "/")
  · dosyası olmayan / kutusuz / şüpheli-etiketli kayıt ELENİR
  · grup       = sahne(it)  (sızıntı önleyici: eid varsa e:<eid>, yoksa t:cam/gun/saat[:3])

DİKKAT — hangi dosya "etiket seti" DEĞİL:
  /mnt/data/sera-arsiv/gate/labels.json  → 119 kayıtlık OLAY denetim dosyası (TP/FP),
  etiket seti değildir. Buradaki yukle() ona ASLA bakmaz.

ASIL SET: scratchpad/labels_946.json + label_queue_946.json (946 etiket, VPS'ten çekildi).
ESKİ SET: scratchpad/labels.json + label_queue.json (763) — "v2 ne biliyordu" referansı.

API (diğer modüller buna göre yazıyor — imzayı bozma):
    yukle(surum="946")                 -> {fid: {"v","u","ts"}}
    kuyruk(surum="946")                -> {fid: kayit}
    vps_senkron(hedef_yol, ...)        -> (n_eski, n_yeni)      SADECE OKUMA (scp indirir)
    birlestir_kayitlar(etiket, kuyruk) -> [{fid,p,box,cam,et,grup,hd}]
    dagilim(etiketler)                 -> {"var","yok","kutu","cok"}
    supheli_etiketler()                -> set(fid)
"""

import os
import json
import shutil
import subprocess
import collections

# ---------------------------------------------------------------- ayarlar
# sera.ayar TEK gerçek kaynaktır — SERT import, yedek literal YOK.
# ⚠ 2 Ağu: VPS adresi, ssh anahtarı ve /opt/sera burada bir KEZ DAHA yazılıydı;
#   ayar.py'deki değerlerin ikinci kopyasıydı. Kaldırıldı.
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


ARSIV     = _a("ARSIV")
GATE      = _a("GATE")
SCRATCH   = _a(("SCRATCH", "ETIKET_DIZIN"))

# ASIL set (946) ve eski set (763). Sürüm adı → (etiket dosyası, kuyruk dosyası)
SURUMLER = {
    # 3 Ağu: ASIL set 1113'e çıktı (Alperen 167 kare daha etiketledi; k2 19->49).
    "1113": (_a("ETIKET"), _a("KUYRUK")),
    "946": (_a("ETIKET_946"), _a("KUYRUK_946")),
    "763": (_a("ETIKET_763"), _a("KUYRUK_763")),
}
VARSAYILAN_SURUM = _a("ETIKET_SURUM")

# VPS — SADECE OKUMA. Etiket uygulaması buraya yazar, biz sadece indiririz.
VPS         = _a(("VPS_HOST", "VPS"))
SSH_ANAHTAR = _a(("VPS_ANAHTAR", "SSH_ANAHTAR"))
VPS_KOK     = _a("VPS_KOK")
VPS_ETIKET  = _a("VPS_ETIKET")      # state_service:LABEL_FILE
VPS_KUYRUK  = _a("VPS_KUYRUK")      # state_service:LABEL_QUEUE
VPS_ONEK    = _a("VPS_ONEK")        # yol çevirisi: → ARSIV + "/"

DENETIM_JSON = _a("ETIKET_DENETIM")

ETIKET_DEGERLERI = ("var", "yok", "kutu", "cok")


# ---------------------------------------------------------------- sahne grubu
# TEK GERÇEK KAYNAK sera.arsiv.sahne — kopyalamıyoruz. Bu anahtar GroupKFold'un bölme
# anahtarıdır; iki dosyada iki farklı hâli olursa ölçüm sessizce sızıntıya döner.
# (arsiv.sahne gövdesi train_verifier3.py:sahne / oof_esik.py:sahne ile birebir aynıdır.)
from .arsiv import sahne as sahne_grubu  # noqa: E402


# ---------------------------------------------------------------- okuma
def _cozumle(surum, indeks):
    """surum → dosya yolu. '946'/'763' bilinen sürüm; onun dışındaki her şey YOL sayılır."""
    surum = surum or VARSAYILAN_SURUM
    if surum in SURUMLER:
        return SURUMLER[surum][indeks]
    return surum


def yukle(surum=None):
    """Etiketleri oku → {fid: {"v": var|yok|kutu|cok, "u":.., "ts":..}}.

    surum: "946" (ASIL) · "763" (eski) · doğrudan dosya yolu.
    """
    yol = _cozumle(surum, 0)
    with open(yol) as f:
        return json.load(f)


def kuyruk(surum=None):
    """Etiket kuyruğunu oku → {fid: kayit}. Kayıtta p/cam/gun/saat/pbox/kutu/hd/eid bulunur."""
    yol = _cozumle(surum, 1)
    with open(yol) as f:
        d = json.load(f)
    items = d["items"] if isinstance(d, dict) else d
    return {it["fid"]: it for it in items}


def supheli_etiketler(yol=None):
    """gate/etiket_denetim.json'daki şüpheli fid'ler (3 gövdenin ORTAK itirazı) → eğitimden çıkar.

    train_verifier3.py:main()'deki try/except bloğunun aynısı: dosya yoksa boş küme,
    iş durmaz (mantık korundu).
    """
    try:
        with open(yol or DENETIM_JSON) as f:
            return {x["fid"] for x in json.load(f)["suphe"]}
    except Exception:
        return set()


def yerel_yol(p):
    """VPS yolunu arşiv yoluna çevir: /opt/sera/... → /mnt/data/sera-arsiv/..."""
    return p.replace(VPS_ONEK, ARSIV.rstrip("/") + "/")


# ---------------------------------------------------------------- VPS senkronu
def _sayi(veri):
    """labels.json (dict) veya label_queue.json ({"items":[...]}) için kayıt sayısı."""
    if isinstance(veri, dict):
        return len(veri.get("items", veri))
    return len(veri)


def vps_senkron(hedef_yol, uzak=None, kuru=False, zaman_asimi=120):
    """VPS'teki etiket dosyasını yerele indir. SADECE OKUMA — VPS'e hiçbir şey yazılmaz.

    hedef_yol : yerel hedef (varsa üzerine yazılır, ama önce JSON doğrulanır)
    uzak      : uzak yol (varsayılan /opt/sera/labels.json; kuyruk için VPS_KUYRUK ver)
    kuru      : True → komutu yazdır, indirme YAPMA. (n_eski, n_eski) döner.

    Dönüş: (n_eski, n_yeni) — indirmeden önceki ve sonraki kayıt sayısı.
    Bozuk/eksik indirme hedefi BOZMAZ: geçici dosyaya inilir, JSON parse edilir, sonra taşınır.
    """
    uzak = uzak or VPS_ETIKET
    n_eski = 0
    if os.path.exists(hedef_yol):
        try:
            with open(hedef_yol) as f:
                n_eski = _sayi(json.load(f))
        except Exception:
            n_eski = 0

    komut = ["scp", "-q", "-i", SSH_ANAHTAR, "-o", "BatchMode=yes",
             "%s:%s" % (VPS, uzak), hedef_yol + ".indirilen"]
    if kuru:
        print("KURU ÇALIŞMA — çalıştırılmadı:\n  " + " ".join(komut), flush=True)
        return n_eski, n_eski

    gecici = hedef_yol + ".indirilen"
    try:
        r = subprocess.run(komut, capture_output=True, text=True, timeout=zaman_asimi)
        if r.returncode != 0:
            raise RuntimeError("scp basarisiz (%d): %s" % (r.returncode, (r.stderr or "")[:200]))
        with open(gecici) as f:
            n_yeni = _sayi(json.load(f))       # bozuksa burada patlar, hedefe dokunmadan
        os.makedirs(os.path.dirname(os.path.abspath(hedef_yol)) or ".", exist_ok=True)
        shutil.move(gecici, hedef_yol)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)
    print("VPS senkron: %s → %s   (%d → %d kayit)" % (uzak, hedef_yol, n_eski, n_yeni), flush=True)
    return n_eski, n_yeni


# ---------------------------------------------------------------- birleştirme
def birlestir_kayitlar(etiket, kuyruk_, haric=None, eski_etiket=None, sessiz=True):
    """Etiket + kuyruk → değerlendirilebilir kayıt listesi.

    GÖVDE train_verifier3.py:main()'in kayıt döngüsünden devralındı; eleme sırası korundu:
      1. şüpheli etiket (haric)  2. kuyrukta yok  3. kutusuz  4. dosya diskte yok

    haric       : elenecek fid kümesi. None → supheli_etiketler() (train_verifier3 davranışı).
                  Hiç eleme istemiyorsan set() ver.
    eski_etiket : verilirse her kayda "eskide" (bool) eklenir — "yeni etiketler ne kazandırdı"
                  tek-değişkenli kıyası için (train_verifier3.py). Verilmezse alan eklenmez.

    Dönüş: [{"fid","p","box","cam","et","grup","hd"[,"eskide"]}]
    """
    if haric is None:
        haric = supheli_etiketler()
    haric = set(haric or ())
    if haric and not sessiz:
        print("denetimden gelen supheli etiket: %d (egitimden cikariliyor)" % len(haric))

    kay = []
    for fid, ent in etiket.items():
        if fid in haric:
            continue
        it = kuyruk_.get(fid)
        if not it:
            continue
        box = it.get("pbox") or it.get("kutu")     # ÜRETİM kutusu; ywbox (YOLO-World) DEĞİL
        if not box:
            continue
        p = yerel_yol(it["p"])
        if not os.path.exists(p):
            continue
        k = {"fid": fid, "p": p, "box": box, "cam": it.get("cam"),
             "et": ent["v"] if isinstance(ent, dict) else ent,
             "grup": sahne_grubu(it), "hd": bool(it.get("hd"))}
        if eski_etiket is not None:
            k["eskide"] = fid in eski_etiket
        kay.append(k)
    return kay


def dagilim(etiketler):
    """Etiket dağılımı → {"var":n,"yok":n,"kutu":n,"cok":n} (+ varsa başka değerler).

    Girdi: yukle() sözlüğü {fid:{"v":..}} · birlestir_kayitlar() listesi · düz değer listesi.
    """
    if isinstance(etiketler, dict):
        deg = [(v["v"] if isinstance(v, dict) else v) for v in etiketler.values()]
    else:
        deg = [(x["et"] if isinstance(x, dict) else x) for x in etiketler]
    c = collections.Counter(deg)
    out = {a: int(c.get(a, 0)) for a in ETIKET_DEGERLERI}
    for a, n in c.items():                         # beklenmedik değer olursa gizlenmesin
        if a not in out:
            out[a] = int(n)
    return out


if __name__ == "__main__":
    import sys
    surum = sys.argv[1] if len(sys.argv) > 1 else VARSAYILAN_SURUM
    lab, q = yukle(surum), kuyruk(surum)
    sup = supheli_etiketler()
    kay = birlestir_kayitlar(lab, q, sessiz=False)
    print("surum %s · etiket %d · kuyruk %d · supheli %d" % (surum, len(lab), len(q), len(sup)))
    print("degerlendirilebilir kayit: %d" % len(kay))
    print("etiket dagilimi (ham)  :", dagilim(lab))
    print("etiket dagilimi (kayit):", dagilim(kay))

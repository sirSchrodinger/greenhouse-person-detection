# -*- coding: utf-8 -*-
"""
sera.egitim — eğitim hattının adımları: TARA → GOMU → EGIT → DISAVER (+ KUYRUK).

"Yarın 'sistemi baştan eğit' diyen biri ne çalıştıracağını bilmiyor" derdinin cevabı.
Sıra kafada değil, burada.

DEVRALINAN (yeniden yazılmadı, taşındı):
  · tara()      ← sera_pipeline.py:adim_tara()      (+ _tara_yaz birleştirme kilidi)
  · gomu()      ← sera_pipeline.py:adim_gomu()
  · egit()      ← train_verifier3.py:main()          (A/B tek değişkenli kıyas + varyant korunur)
                  + sera_pipeline.py:adim_egit()     (TÜM kayıtlar için OOF, 'kutu' skorlanır)
  · disaver()   ← sera_pipeline.py:adim_disaver()    (yarım-uygulama gerileme kontrolü DAHİL)
  · kuyruk()    ← sera_pipeline.py:adim_kuyruk()     (kuyruk_sirala.py aktif öğrenme mantığı)

İKİ SERT KURAL
  1. ÜRETİM VARYANTI KORUNUR. "OOF AUC'si yüksek olanı seç" demek varyantı ölçüm
     protokolüne göre oynatır; üretimdeki v2 `cok HARIC` ile eğitildi. Tek değişken YENİ
     ETİKETLER olmalı (train_verifier3.py:239-246'daki düzeltme).
  2. CANLI DOSYAYA YAZMAZ. Çıktı gate/pipeline/ altına gider. weights/verifier_head.json
     ve VPS ancak `sera.dagit` ile, kuru turdan sonra değişir.
"""
import os
import re
import time
import collections

import numpy as np

from . import ayar
from . import rapor
from . import arsiv
from . import etiket
from . import olcum

HAT = os.path.join(ayar.GATE, "pipeline")
TARA_JSON = os.path.join(HAT, "tara.json")
GOMU_ETIKET = os.path.join(HAT, "gomu_etiket.npz")
GOMU_TARA = os.path.join(HAT, "gomu_tara.npz")
GOMU_KUYRUK = os.path.join(HAT, "gomu_kuyruk.npz")
EGIT_JSON = os.path.join(HAT, "egit.json")
KUYRUK_JSON = os.path.join(HAT, "kuyruk.json")
KAFA_ADAY = os.path.join(HAT, "verifier_head_yeni.json")
HACIM_KURU = os.path.join(ayar.GATE, "hacim_kuru.json")     # regresyon referansı

DET_TARA = ayar.DET_TARA          # 0.05 — taramada kutu ÜRETME eşiği (ateşleme değil)
MIN_ALAN = ayar.MIN_ALAN          # 0.0018
DET_ATES = ayar.DET_ATES          # 0.52

# tara() sonundaki dedektör regresyonunun CANLI aşaması (bkz. _tara_regresyon docstring'i).
# 12 kare ≈ 3.5 sn; testin hata üretebilmesinin bedeli bu. 0 = canlı aşama kapalı (ayni=None).
REG_CANLI_N = int(ayar._oku("REG_CANLI_N", 12))
REG_TOHUM = int(ayar._oku("REG_TOHUM", 20260802))


# ============================================================ yardımcı
def _npz_oku(yol, anahtar="fid"):
    if not os.path.exists(yol):
        return {}
    z = np.load(yol, allow_pickle=True)
    return {str(k): v for k, v in zip(z[anahtar], z["F"])}


def _npz_yaz(yol, d, anahtar="fid"):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    ks = list(d.keys())
    np.savez_compressed(yol, F=np.array([d[k] for k in ks], np.float32),
                        **{anahtar: np.array(ks, object)})


def kayitlar(surum=None, eski_surum="763", haric=None, sessiz=False):
    """Etiketli kayıtlar + ölçüm için gereken alanlar (det/gun/saat/gece/eid).

    etiket.birlestir_kayitlar() gövdeyi verir; buradaki zenginleştirme kuyruk öğesinden
    gelir (pskor = ÜRETİM dedektörünün o karedeki skoru) — sera_pipeline.py:etiketli_kayitlar.
    """
    surum = surum or ayar.ETIKET_SURUM
    lab = etiket.yukle(surum)
    q = etiket.kuyruk(surum)
    eski = etiket.yukle(eski_surum) if eski_surum else None
    kay = etiket.birlestir_kayitlar(lab, q, haric=haric, eski_etiket=eski, sessiz=sessiz)
    for k in kay:
        it = q.get(k["fid"], {})
        gun, saat = it.get("gun"), it.get("saat")
        if not saat:
            g2, s2 = arsiv.zaman_of(k["p"])
            gun, saat = gun or g2, s2
        k["gun"] = gun or "?"
        k["saat"] = saat
        k["eid"] = it.get("eid")
        # ⚠ SIZINTI KANALI (2 Ağu, denetimde bulundu): grup, etiket.birlestir_kayitlar()
        #   içinde HAM kuyruk kaydından hesaplanıyordu. Kuyrukta gun/saat olmayan kayıt
        #   "t:cam/?/?" grubuna düşüyor, ama YUKARIDAKİ zenginleştirme gun/saat'i dosya
        #   yolundan doldurunca grup GÜNCELLENMİYORDU. Sonuç: AYNI SAHNENİN iki karesi
        #   farklı gruplara düşüp farklı fold'lara ayrılabiliyordu — model bir kareyle
        #   eğitilip komşusuyla test ediliyor, AUC şişiyor. Ölçüldü: 862 kaydın 115'inde
        #   grup değişiyor, 109'u aynı sahnede olup farklı gruba düşmüş.
        #   Grup artık zenginleştirmeden SONRA hesaplanır.
        k["grup"] = etiket.sahne_grubu({"eid": k["eid"], "cam": k["cam"],
                                        "gun": k["gun"], "saat": k["saat"]})
        k["det"] = float(it.get("pskor") or 0.0)
        k["gece"] = arsiv.gece({"saat": saat})
    return kay


# ============================================================ 1) TARA
def _tara_yaz(yol, kayit, taranan):
    """tara.json'ı YAZMADAN ÖNCE diskteki hâliyle BİRLEŞTİR — sera_pipeline.py:_tara_yaz.

    İki koşu aynı anda çalışabiliyor (arka planda tam tarama, önde --hizli). Düz yazım
    son yazanı kazandırıp öbür koşunun saatlerce süren karelerini siliyordu.
    """
    d = rapor.joku(yol, None)
    if not d:
        rapor.jyaz(yol, {"kayit": list(kayit.values()), "taranan": sorted(taranan)})
        return
    birlesik = {r["p"]: r for r in d["kayit"]}
    birlesik.update(kayit)
    rapor.jyaz(yol, {"kayit": list(birlesik.values()),
                     "taranan": sorted(set(d["taranan"]) | set(taranan))})


def tara(hizli=False, ornek=300, yeniden=False, kaynak=None, cikti=None, yaz=True):
    """Arşivi ÜRETİM dedektörüyle geç (kutu + skor). Artımlı, önbellekli.

    kaynak : None → tüm arşiv. "timeline"/"dvr_hd"/"diag_hd"/"diag_vps"/"olay" ile sınırla.
    Sonunda gate/hacim_kuru.json'a karşı SAYISAL REGRESYON testi yapar; sapma varsa bağırır.
    """
    import cv2
    from . import dedektor as ded

    cikti = cikti or TARA_JSON
    if yaz:
        rapor.baslik("TARA — arşivi üretim dedektörüyle geç (kutu + skor)")
    onb = rapor.joku(cikti, None) if not yeniden else None
    kayit = {r["p"]: r for r in onb["kayit"]} if onb else {}
    taranan = set(onb["taranan"]) if onb else set()
    if onb and yaz:
        rapor.log("önbellek: %d kare taranmış, %d'sinde kutu var" % (len(taranan), len(kayit)))

    fs = arsiv.kaynaklar()
    if kaynak:
        istenen = set(kaynak) if not isinstance(kaynak, str) else {kaynak}
        fs = [p for p in fs if arsiv.kaynak_adi(p) in istenen]
    if yaz:
        rapor.log("arşivdeki kare: %d   %s" % (len(fs), arsiv.kaynak_sayim(fs)))
    if hizli:
        adim = max(1, len(fs) // max(1, ornek))
        fs = fs[::adim][:ornek]
        if yaz:
            rapor.log("HIZLI MOD: her %d karede 1 -> %d kare (tüm kaynaklar temsil edilir)"
                      % (adim, len(fs)))

    yeni = [p for p in fs if p not in taranan]
    if yaz:
        rapor.log("taranacak yeni kare: %d  (önbellekten atlanan %d)"
                  % (len(yeni), len(fs) - len(yeni)))

    if yeni:
        d = ded.Dedektor()
        t0 = time.time()
        for k, p in enumerate(yeni, 1):
            img = cv2.imread(p)
            taranan.add(p)
            if img is None:
                continue
            ks = d.kutular(img, esik=DET_TARA, min_alan=MIN_ALAN)   # NMS yok, sinirla=True
            if ks:
                en = ks[0]
                gun, saat = arsiv.zaman_of(p)
                kayit[p] = {"p": p, "rel": arsiv.rel(p), "det": round(en["skor"], 4),
                            "box": [round(float(v), 1) for v in en["kutu"]],
                            "n_kutu": len(ks), "cam": arsiv.cam_of(p),
                            "gun": gun or "?", "saat": saat,
                            "kaynak": arsiv.kaynak_adi(p),
                            "hd": bool(max(img.shape[:2]) >= ayar.HD_KENAR),
                            "gece": arsiv.gece({"saat": saat})}
            if yaz:
                rapor.ilerleme(k, len(yeni), t0, "· kutulu %d" % len(kayit))
            if k % 500 == 0:
                _tara_yaz(cikti, kayit, taranan)
        _tara_yaz(cikti, kayit, taranan)

    K = list(kayit.values())
    if yaz:
        tsay = collections.Counter(arsiv.kaynak_adi(p) for p in taranan)
        ksay = collections.Counter(r["kaynak"] for r in K)
        rapor.alt("kaynak kırılımı (kutulu / taranan)")
        rapor.tablo([{"kaynak": s, "kutulu": ksay.get(s, 0), "taranan": tsay[s],
                      "%": "%.0f" % (100.0 * ksay.get(s, 0) / max(1, tsay[s]))}
                     for s in sorted(tsay)])
        rapor.sayac([r["cam"] for r in K], "kamera")
        rapor.sayac([r["gece"] for r in K], "gece/gündüz")

    reg = _tara_regresyon(kayit, yaz=yaz)
    ozet_m = "%d kare tarandı, %d'sinde kutu (%%%.1f)" % (
        len(taranan), len(K), 100.0 * len(K) / max(1, len(taranan)))
    if yaz:
        rapor.ozet("tara", ozet_m, cikti)
    rapor.durum_yaz("tara", ozet_m, {"regresyon": reg})
    return {"kayit": K, "taranan": len(taranan), "regresyon": reg, "ozet": ozet_m,
            "cikti": cikti}


def _tara_regresyon(kayit, yaz=True, canli_n=None, tohum=None):
    """MANTIK KORUNDU MU? gate/hacim_kuru.json ile karşılaştır — İKİ AŞAMALI.

    sera_pipeline.py:431-442'den devralındı, ama oradaki testin ÖLÜ olduğu ölçülerek
    bulundu ve burada onarıldı:

    ⚠ 2 Ağu DENETİM BULGUSU [[feedback_measurement_tautology]]
      Eski hâli SADECE `kayit` sözlüğünü (yani tara.json ÖNBELLEĞİNİ) referansla
      kıyaslıyordu. Önbellek sıcakken `yeni == []` olur, dedektör HİÇ çağrılmaz ve
      test iki DURAN dosyayı karşılaştırır — sonuç her zaman "MANTIK AYNI".
      Kanıt: SERA_DET_ESIK=0.90 SERA_MIN_ALAN=0.5 (dedektörü tamamen bozan ayar) ile
      `tara --hizli` koşuldu; test 800 karede yine "MANTIK AYNI" bastı.
      Bir test hatayı ÜRETEBİLMELİ; üretemiyorsa yeşil rengin bilgi değeri yoktur.

    Aşama 1 (ÖNBELLEK): tara.json ile hacim_kuru.json ortak kareleri — önbellek
      bozulmasını/karışmasını yakalar. Dedektörü çağırmaz.
    Aşama 2 (CANLI): hacim_kuru.json'dan `canli_n` kare CANLI dedektörle YENİDEN skorlanır.
      Mantık sapmasını yakalayan aşama budur. `ayni` artık İKİSİNİ birden ister.

    canli_n : canlı yeniden skorlanacak kare sayısı. Varsayılan 12 — ölçüldü, bu makinede
              kare başına ~0.29 sn, yani ~3.5 sn; `tara` zaten dakikalar süren bir iş,
              bu maliyet gürültüde kalır. 0 verilirse aşama 2 ATLANIR ve `ayni` None olur
              (sessizce yeşil DEĞİL).
    Tolerans: hacim_kuru.json det'i round(...,4), box'ı round(...,1) ile yazılmıştır;
      dolayısıyla bit-birebir bir dedektörde bile det farkı 5e-5'e, kutu farkı 0.05 px'e
      kadar çıkar. Eşikler bunun hemen üstünde (1e-4 / 0.11 px).
    """
    import random

    ref = rapor.joku(HACIM_KURU, None)
    if not ref:
        return None
    R = {r["p"]: r for r in ref["kayit"]}
    ortak = [p for p in R if p in kayit]
    if not ortak:
        return None
    dd = max(abs(R[p]["det"] - kayit[p]["det"]) for p in ortak)
    kb = max(max(abs(x - y) for x, y in zip(R[p]["box"], kayit[p]["box"])) for p in ortak)
    onbellek_ok = bool(dd < 1e-9 and kb < 0.11)

    d = {"ortak": len(ortak), "det_fark": float(dd), "kutu_fark": float(kb),
         "onbellek_ayni": onbellek_ok}

    # ---------------- aşama 2: CANLI yeniden skorlama (testin hata üretebildiği yer)
    n = REG_CANLI_N if canli_n is None else int(canli_n)
    tohum = REG_TOHUM if tohum is None else int(tohum)
    if n <= 0:
        d.update({"canli": None, "ayni": None})
        if yaz:
            rapor.log()
            rapor.log("REGRESYON (önbellek, ortak %d kare): det %.6f · kutu %.2f px" %
                      (len(ortak), dd, kb))
            rapor.log(rapor.kirmizi("  ⚠ CANLI aşama atlandı (canli_n=0) — bu tur "
                                    "dedektör mantığını DOĞRULAMADI"))
        return d

    from . import dedektor as ded
    havuz = [r for r in ref["kayit"] if r.get("box") and os.path.exists(r["p"])]
    random.Random(tohum).shuffle(havuz)
    ornek = havuz[:n]
    det_sapan, cdd, ckb, olculen = [], 0.0, 0.0, 0
    if ornek:
        dd_ = ded.Dedektor()
        for r in ornek:
            k = dd_.en_iyi(r["p"], esik=DET_TARA, min_alan=MIN_ALAN)
            if k is None:                      # referansta kutu vardı, şimdi yok → SAPMA
                det_sapan.append((r["p"], float(r["det"]), None))
                continue
            olculen += 1
            f1 = abs(k["skor"] - float(r["det"]))
            f2 = max(abs(float(x) - float(y)) for x, y in zip(k["kutu"], r["box"]))
            cdd, ckb = max(cdd, f1), max(ckb, f2)
            if f1 > 1e-4:
                det_sapan.append((r["p"], float(r["det"]), float(k["skor"])))
    canli_ok = bool(olculen >= 3 and not det_sapan and cdd < 1e-4 and ckb < 0.11)
    d["canli"] = {"istenen": n, "olculen": olculen, "det_fark": float(cdd),
                  "kutu_fark": float(ckb), "sapan": len(det_sapan), "ayni": canli_ok}
    d["ayni"] = bool(onbellek_ok and canli_ok)

    if yaz:
        rapor.log()
        rapor.log("REGRESYON 1/2 ÖNBELLEK (hacim_kuru.json ile ortak %d kare): "
                  "det %.6f · kutu %.2f px  -> %s"
                  % (len(ortak), dd, kb,
                     rapor.yesil("aynı") if onbellek_ok else rapor.kirmizi("⚠ SAPMA")))
        if olculen < 3:
            rapor.log("REGRESYON 2/2 CANLI: %s"
                      % rapor.kirmizi("çalıştırılamadı (ölçülen %d kare) — "
                                      "dedektör mantığı DOĞRULANMADI" % olculen))
        else:
            rapor.log("REGRESYON 2/2 CANLI (%d kare YENİDEN skorlandı): det %.2e · "
                      "kutu %.3f px · sapan %d  -> %s"
                      % (olculen, cdd, ckb, len(det_sapan),
                         rapor.yesil("MANTIK AYNI") if canli_ok
                         else rapor.kirmizi("⚠ MANTIK SAPMIŞ")))
        for p, e, y in det_sapan[:5]:
            rapor.log(rapor.kirmizi("     %s: %.4f -> %s" % (arsiv.rel(p), e, y)))
    return d


# ============================================================ 2) GOMU
def gomu(surum=None, hizli=False, ornek=300, yeniden=False, yaz=True):
    """DINOv2 gömüleri (artımlı): (a) etiketli kareler, (b) taramada kutu çıkan kareler.

    (a) doğrulayıcı eğitimi için, (b) hacim projeksiyonu + aktif öğrenme için.
    Önbellek zinciri: gate/pipeline/gomu_etiket.npz → gate/oof_gomu_946.npz → gate/oof_gomu.npz
    (İLKİ kazanır ve YAZMA yolu odur; gate/oof_gomu_946.npz'e DOKUNULMAZ.)
    """
    import cv2
    from . import dogrulayici as dog

    if yaz:
        rapor.baslik("GOMU — kutu kırpmalarının DINOv2 gömüleri (önbellekli)")
    os.makedirs(HAT, exist_ok=True)
    if yeniden:
        for p in (GOMU_ETIKET, GOMU_TARA):
            if os.path.exists(p):
                os.remove(p)

    kay = kayitlar(surum, sessiz=not yaz)
    d = dog.Dogrulayici()
    kay, F = d.gomuler(kay, onbellek_yolu=[GOMU_ETIKET, ayar.GOMU_946, ayar.GOMU_763],
                       ilerleme=40 if yaz else 0)
    if yaz:
        rapor.log("etiketli gömü: %d vektör -> %s" % (len(kay), GOMU_ETIKET))

    # --- tarama kayıtlarının gömüleri ---
    T = rapor.joku(TARA_JSON, None)
    GT = _npz_oku(GOMU_TARA, "yol")
    if not T:
        if yaz:
            rapor.log("tara.json yok -> tarama gömüleri atlandı (önce `tara` çalıştır)")
    else:
        kayit = sorted(T["kayit"], key=lambda r: -r["det"])
        if hizli:
            kayit = kayit[:max(40, ornek // 3)]
            if yaz:
                rapor.log("HIZLI MOD: tarama gömüsü en yüksek skorlu %d kareyle sınırlı"
                          % len(kayit))
        eksik = [r for r in kayit if r["p"] not in GT]
        if yaz:
            rapor.log("tarama gömüsü: %d hazır · %d eksik (~%.0f dk)"
                      % (len(kayit) - len(eksik), len(eksik), len(eksik) * 0.25 / 60.0))
        if eksik:
            t0 = time.time()
            for i, r in enumerate(eksik, 1):
                img = cv2.imread(r["p"])
                v = d.gomu(img, r["box"]) if img is not None else None
                if v is not None:
                    GT[r["p"]] = v
                if i % 200 == 0:
                    _npz_yaz(GOMU_TARA, GT, "yol")
                if yaz:
                    rapor.ilerleme(i, len(eksik), t0)
            _npz_yaz(GOMU_TARA, GT, "yol")
        if yaz:
            rapor.log("gomu_tara.npz: %d vektör" % len(GT))

    ozet_m = "etiket %d gömü · tarama %d gömü" % (len(kay), len(GT))
    if yaz:
        rapor.ozet("gomu", ozet_m, GOMU_ETIKET)
    rapor.durum_yaz("gomu", ozet_m)
    return {"etiket": len(kay), "tarama": len(GT), "kayit": kay, "F": F, "ozet": ozet_m}


# ============================================================ 3) EGIT
def egit(surum=None, eski_surum="763", permutasyon_n=0, cikti=None, kafa_cikti=None,
         yaz=True):
    """Doğrulayıcıyı eğit. ÜRETİM VARYANTI KORUNUR + TEK DEĞİŞKENLİ KIYAS.

    A) eğitim dilimine SADECE eski sürümden düşen örnekler   (= eski model ne biliyordu)
    B) eğitim dilimine hepsi                                  (= yeni model)
    AYNI fold, AYNI test dilimleri. Karar AUC ile DEĞİL, canlı çalışma noktasında ve
    eşleştirilmiş tabloda verilir.

    Çıktı: gate/pipeline/egit.json (kayıt başına OOF skor) + aday kafa JSON.
    ÜRETİM DOSYASINA (weights/verifier_head.json) YAZMAZ.
    """
    from sklearn.metrics import roc_auc_score
    from . import dogrulayici as dog

    cikti = cikti or EGIT_JSON
    kafa_cikti = kafa_cikti or KAFA_ADAY
    surum = surum or ayar.ETIKET_SURUM
    if yaz:
        rapor.baslik("EGIT — doğrulayıcı, GroupKFold (grup = olay / kamera-gün-saat sahnesi)")

    sup = etiket.supheli_etiketler()
    kay = kayitlar(surum, eski_surum, sessiz=not yaz)
    if yaz:
        rapor.log("etiket seti: %s · değerlendirilebilir kayıt %d (eski setten %d · YENİ %d)"
                  % (surum, len(kay), sum(1 for k in kay if k.get("eskide")),
                     sum(1 for k in kay if not k.get("eskide"))))
        if sup:
            rapor.log("denetimden gelen şüpheli etiket: %d çıkarıldı" % len(sup))
            rapor.log("  ⚠ 'çıkarınca AUC arttı' tek başına kanıt değil; bunlar gözle bakılıp "
                      "hata olduğu görülen etiketler")
        rapor.sayac([k["et"] for k in kay], "etiket dağılımı")

    d = dog.Dogrulayici()
    kay, F = d.gomuler(kay, onbellek_yolu=[GOMU_ETIKET, ayar.GOMU_946, ayar.GOMU_763],
                       ilerleme=40 if yaz else 0)
    et = np.array([k["et"] for k in kay])
    cam = np.array([k["cam"] for k in kay])
    grp = np.array([k["grup"] for k in kay])
    eskide = np.array([bool(k.get("eskide")) for k in kay])
    if len(kay) < 20 or len(set(grp.tolist())) < 2:
        raise SystemExit("eğitim için yeterli etiket/sahne yok (n=%d, sahne=%d)"
                         % (len(kay), len(set(grp.tolist()))))
    if yaz:
        rapor.log("gömü: %s · sahne grubu: %d (sızıntı önleyici bölme birimi)"
                  % (F.shape, len(set(grp.tolist()))))

    sonuc = {"uretim": "sera.egitim", "etiket_surum": surum, "n_toplam": int(len(kay)),
             "n_yeni_etiket": int((~eskide).sum())}

    for ad, poz in (("cok HARIC", {"var"}), ("cok POZITIF", {"var", "cok"})):
        m = np.isin(et, list(poz | {"yok"}))
        y = np.isin(et, list(poz)).astype(int)[m]
        Fm, gm, cm, em = F[m], grp[m], cam[m], eskide[m]
        if len(set(gm.tolist())) < 2 or len(set(y.tolist())) < 2:
            continue
        oof_a, oof_b, ok = olcum.oof_ab(Fm, y, gm, em)
        ya, sa, sb = y[ok], oof_a[ok], oof_b[ok]
        if len(set(ya.tolist())) < 2:
            continue
        auc_a, auc_b = float(roc_auc_score(ya, sa)), float(roc_auc_score(ya, sb))
        tab = olcum.eslestirilmis(ya, sa, sb, "eski%s" % eski_surum, "yeni%s" % surum)
        cn = {"eski%s" % eski_surum: olcum.canli_nokta(ya, sa),
              "yeni%s" % surum: olcum.canli_nokta(ya, sb)}
        kd = olcum.kamera_disla(Fm, y, cm)
        if yaz:
            rapor.alt("%s — ortak test n=%d (poz %d / neg %d)"
                      % (ad, len(ya), int(ya.sum()), int(len(ya) - ya.sum())))
            rapor.log("  OOF AUC   eski%s %.4f  ->  yeni%s %.4f"
                      % (eski_surum, auc_a, surum, auc_b))
            e0, e1 = cn["eski%s" % eski_surum], cn["yeni%s" % surum]
            rapor.log("  CANLI NOKTA (eşik %.2f): kaçırma %d -> %d  |  yanlış-geçen %d -> %d"
                      % (e0["esik"], e0["kacirma"], e1["kacirma"],
                         e0["yanlis_gecen"], e1["yanlis_gecen"]))
            rapor.log("  EŞLEŞTİRİLMİŞ ÇALIŞMA NOKTASI (kazanc>0 = yeni model daha iyi):")
            rapor.tablo(tab, ["sabit", "eski%s" % eski_surum, "yeni%s" % surum, "kazanc"])
            if kd:
                rapor.log("  KAMERA-DIŞLA (genelleme):")
                rapor.tablo([{"kamera": k, "auc": "%.4f" % v["auc"], "n": v["n"],
                              "poz": v["poz"]} for k, v in kd.items()])
        sonuc[ad] = {"auc_eski": auc_a, "auc_yeni": auc_b, "n_ortak": int(len(ya)),
                     "poz": int(ya.sum()), "eslestirilmis": tab, "kamera_disla": kd,
                     "canli_nokta": cn}

    if "cok HARIC" not in sonuc and "cok POZITIF" not in sonuc:
        raise SystemExit("varyant kurulamadı (yeterli grup/sınıf yok)")

    # --- ÜRETİM VARYANTI KORUNUR (train_verifier3.py:239-246) ---
    kazanan = (rapor.joku(ayar.KAFA, {}) or {}).get("egitim", {}).get("varyant") or "cok HARIC"
    if kazanan not in sonuc:
        kazanan = list(k for k in ("cok HARIC", "cok POZITIF") if k in sonuc)[0]
    poz_set = {"var"} if kazanan == "cok HARIC" else {"var", "cok"}
    if yaz:
        rapor.log()
        rapor.log("ÜRETİM VARYANTI KORUNDU: %s  (OOF AUC %.4f)"
                  % (kazanan, sonuc[kazanan]["auc_yeni"]))
        rapor.log("  ⚠ Varyantı ölçüme bakarak değiştirmek TUTARSIZ olur: v2 kendi CV'sinde "
                  "'cok HARIC' seçti; protokol değişince sıralama dönüyor. 'cok' pozitif mi "
                  "sorusu ayrı bir ürün kararı.")

    # --- TÜM kayıtlar için OOF (sera_pipeline.py:619-636): 'kutu' skorlanır ama eğitmez ---
    y_all = np.isin(et, list(poz_set)).astype(int)
    egitilebilir = np.isin(et, list(poz_set | {"yok"}))
    oof, _ = olcum.oof(F, y_all, grp, egitilebilir=egitilebilir)
    var = ~np.isnan(oof)
    m_auc = var & egitilebilir
    auc_oof = float(roc_auc_score(y_all[m_auc], oof[m_auc]))
    if yaz:
        rapor.log("OOF skor üretildi: %d/%d kayıt · OOF AUC (%s, sahne-dışla) %.4f  n=%d"
                  % (int(var.sum()), len(kay), kazanan, auc_oof, int(m_auc.sum())))

    # --- NEGATİF KONTROL (isteğe bağlı, egit içinde de çalıştırılabilir) ---
    perm = None
    if permutasyon_n:
        if yaz:
            rapor.alt("NEGATİF KONTROL (%d karıştırma)" % permutasyon_n)
        perm = olcum.permutasyon(F[egitilebilir], y_all[egitilebilir], grp[egitilebilir],
                                 n=permutasyon_n, sessiz=not yaz)
        if yaz:
            rapor.log("  " + (rapor.yesil("GEÇTİ") if perm.get("gecti")
                              else rapor.kirmizi("GEÇMEDİ: " + perm.get("sebep", "?"))))

    # --- NİHAİ model: tüm veri, korunan varyant ---
    m = np.isin(et, list(poz_set | {"yok"}))
    sc, clf = olcum._fold_egit(F[m], y_all[m])
    model = {"mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(),
             "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0])}

    cik = {"surum": "sera.egitim-" + time.strftime("%Y-%m-%d"), "varyant": kazanan,
           "etiket_surum": surum, "auc_oof": auc_oof,
           "auc_yeni": sonuc[kazanan]["auc_yeni"], "auc_eski": sonuc[kazanan]["auc_eski"],
           "kamera_disla": sonuc[kazanan]["kamera_disla"], "varyantlar": sonuc,
           "n": len(kay), "supheli_cikarilan": len(sup), "permutasyon": perm,
           "model": model,
           "kayit": [{"fid": k["fid"], "rel": arsiv.rel(k["p"]), "et": k["et"],
                      "cam": k["cam"], "gun": k["gun"], "saat": k["saat"],
                      "gece": k["gece"], "det": k["det"], "hd": k["hd"], "grup": k["grup"],
                      "eskide": bool(k.get("eskide")),
                      "oof": None if np.isnan(oof[i]) else float(oof[i])}
                     for i, k in enumerate(kay)]}
    rapor.jyaz(cikti, cik)

    kafa = _kafa_paketle(model, cik, kafa_cikti)
    reg = _kafa_regresyon(model, yaz=yaz)
    cik["kafa_regresyon"] = reg
    rapor.jyaz(cikti, cik)

    ozet_m = ("%s · OOF AUC %.4f (eski %.4f) · n=%d · aday kafa %s"
              % (kazanan, auc_oof, sonuc[kazanan]["auc_eski"], len(kay),
                 os.path.basename(kafa)))
    if yaz:
        rapor.ozet("egit", ozet_m, cikti)
        rapor.log("aday kafa: %s   (ÜRETİM DOSYASINA DOKUNULMADI)" % kafa)
    rapor.durum_yaz("egit", ozet_m)
    return cik


def _kafa_paketle(model, cik, yol):
    """Aday doğrulayıcı kafası. train_verifier3.py:255-265 alan düzeni korunur."""
    h = dict(rapor.joku(ayar.KAFA, {}) or {})
    h.update({
        "govde": "dinov2_vitb14", "boyut": len(model["coef"]),
        "mean": model["mean"], "scale": model["scale"],
        "coef": model["coef"], "intercept": model["intercept"],
        "esik_guvenli": ayar.DOG_ESIK, "esik_agresif": ayar.DOG_ESIK_AGRESIF, "esik_cam": {},
        "kirp": {"W": ayar.KIRP_W, "H": ayar.KIRP_H, "PAD": ayar.PAD, "giris": ayar.GIRIS},
        "egitim": {"n": cik["n"], "varyant": cik["varyant"], "auc_oof": cik["auc_oof"],
                   "kamera_disla": cik["kamera_disla"],
                   "surum": cik["surum"], "etiket_surum": cik["etiket_surum"],
                   "kutu": "uretim(pbox)", "uretici": "sera.egitim"},
    })
    rapor.jyaz(yol, h)
    return yol


def _kafa_regresyon(model, referans=None, yaz=True):
    """MANTIK KORUNDU MU? Aday kafayı train_verifier3.py'nin ürettiği v3 kafasıyla kıyasla.

    Aynı etiket seti + aynı varyant + aynı hiperparametre → katsayılar birebir olmalı.
    """
    referans = referans or ayar.KAFA_V3
    r = rapor.joku(referans, None)
    if not r or "coef" not in r:
        return None
    try:
        dc = float(np.max(np.abs(np.array(model["coef"]) - np.array(r["coef"]))))
        db = abs(model["intercept"] - float(r["intercept"]))
        dm = float(np.max(np.abs(np.array(model["mean"]) - np.array(r["mean"]))))
    except Exception:
        return None
    ok = bool(dc < 1e-6 and db < 1e-6 and dm < 1e-6)
    if yaz:
        rapor.log("KAFA REGRESYONU (%s): katsayı fark %.3g · sabit %.3g · ortalama %.3g -> %s"
                  % (os.path.basename(referans), dc, db, dm,
                     rapor.yesil("BİREBİR AYNI") if ok
                     else rapor.sari("farklı (etiket seti/varyant farklıysa beklenir)")))
    return {"referans": referans, "coef_fark": dc, "intercept_fark": db,
            "mean_fark": dm, "ayni": ok}


# ============================================================ 4) DISAVER
def disaver(egit_json=None, olc_json=None, cikti=None, yaz=True):
    """Aday kafayı paketle + YARIM UYGULAMA GERİLEMESİNİ ölç. sera_pipeline.py:adim_disaver.

    ⚠ ÖNERİ İKİ PARÇALI: bu dosya yalnız doğrulayıcı eşiğini taşır; det eşiği
    vps/person_watch*.py içinde SABİT. Yarısını kurmak tabloda BUGÜNDEN KÖTÜ çıkabilir.
    Bu fonksiyon KURMAZ — kurma işi sera.dagit'te (kuru tur + otomatik geri alma).
    """
    egit_json = egit_json or EGIT_JSON
    olc_json = olc_json or olcum.OLC_JSON
    cikti = cikti or KAFA_ADAY
    E = rapor.joku(egit_json, None)
    if not E:
        raise SystemExit("egit.json yok — önce `egit` çalıştır")
    O = rapor.joku(olc_json, None)
    if yaz:
        rapor.baslik("DISAVER — aday kafa + yarım-uygulama gerileme kontrolü")
        if not O:
            rapor.log("⚠ olc.json yok -> eşik önerisi olmadan, mevcut eşikle paketleniyor")

    on = (O or {}).get("oneri") or {}
    yol = _kafa_paketle(E["model"], E, cikti)
    if yaz:
        rapor.log("yazıldı %s  (doğrulayıcı eşiği %.2f · dedektör eşik önerisi %s)"
                  % (yol, ayar.DOG_ESIK, on.get("det")))

    gerileme = None
    if O and on.get("det") is not None:
        izg = (O.get("tablolar") or {}).get("KARE düzeyi (insan VAR mı)") or []

        def _bul(dt, dg):
            for r in izg:
                if abs(r["det"] - dt) < 1e-9 and r["dog"] == dg:
                    return r
            return None

        def _e(v):
            return "cam" if v is None else "%.2f" % v

        simdi, yarim, tam = (_bul(DET_ATES, None), _bul(DET_ATES, on["dog"]),
                             _bul(on["det"], on["dog"]))
        det_degisiyor = abs(float(on["det"]) - DET_ATES) > 1e-9
        if simdi and yarim and tam and det_degisiyor:
            if yaz:
                rapor.log()
                rapor.log("⚠ ÖNERİ İKİ PARÇALI — bu dosya SADECE doğrulayıcı eşiğini taşır:")
                rapor.tablo([
                    {"senaryo": "bugün", "det": "%.2f" % DET_ATES, "dog": "cam",
                     "yakalanan": simdi["yakalanan"], "yanlış": simdi["yanlis"]},
                    {"senaryo": "bu dosya tek başına", "det": "%.2f" % DET_ATES,
                     "dog": _e(on["dog"]), "yakalanan": yarim["yakalanan"],
                     "yanlış": yarim["yanlis"]},
                    {"senaryo": "tam öneri", "det": "%.2f" % on["det"],
                     "dog": _e(on["dog"]), "yakalanan": tam["yakalanan"],
                     "yanlış": tam["yanlis"]}])
                rapor.log("   det eşiği vps/person_watch*.py içinde; BU DOSYAYLA DEĞİŞMEZ.")
                if on["dog"] is None:
                    # Öneri doğrulayıcı eşiğine DOKUNMUYOR (kamera eşiği kalıyor) — o hâlde
                    # bu dosyayı kurmak öneriden HİÇBİR ŞEY uygulamaz, kazanç det'te.
                    rapor.log(rapor.sari(
                        "   ⚠ Öneri doğrulayıcı eşiğini DEĞİŞTİRMİYOR (kamera eşiği kalıyor): "
                        "kazancın tamamı det %.2f -> %.2f'te. Bu kafayı kurmak öneriden "
                        "hiçbir şey uygulamaz." % (DET_ATES, on["det"])))
            if yarim["yakalanan"] < simdi["yakalanan"] or yarim["yanlis"] > simdi["yanlis"]:
                gerileme = {"simdi": simdi, "yarim": yarim, "tam": tam}
                if yaz:
                    rapor.log(rapor.kirmizi(
                        "   ⛔ Tek başına kurulursa BUGÜNDEN KÖTÜ olur (%d -> %d yakalanan)."
                        % (simdi["yakalanan"], yarim["yakalanan"])))

    if os.path.exists(ayar.DINOV2):
        if yaz:
            rapor.log("ONNX gövde var: %s (%.0f MB) — yeniden dışa aktarım GEREKMİYOR"
                      % (ayar.DINOV2, os.path.getsize(ayar.DINOV2) / 1e6))
    elif yaz:
        rapor.log(rapor.kirmizi("ONNX gövde YOK") + " -> export_verifier.py'nin dışa aktarım "
                  "bölümü elle çağrılmalı (torch.hub ile indirir, ağ ister).")
        rapor.log("  ⚠ export_verifier.py OTOMATİK ÇAĞRILMIYOR: kendi kafasını da eğitip "
                  "weights/verifier_head.json'u v1 mantığıyla ÜZERİNE YAZIYOR.")

    ozet_m = "aday kafa hazır%s" % (" · YARIM UYGULAMA GERİLEME" if gerileme else "")
    if yaz:
        rapor.ozet("disaver", ozet_m, yol)
        rapor.log("KURULMADI (canlı dosyaya dokunulmadı). Kurmak için: sera_cli.py dagit "
                  "--kafa %s" % yol)
    rapor.durum_yaz("disaver", ozet_m)
    return {"kafa": yol, "gerileme": gerileme, "oneri": on, "ozet": ozet_m}


# ============================================================ 5) KUYRUK
def kuyruk(surum=None, hizli=False, ornek=300, yeniden=False, cikti=None, yaz=True):
    """Etiketlenecek kareleri AKTİF ÖĞRENME ile sırala. sera_pipeline.py:adim_kuyruk.

    Sıralama: kararsızlık (|skor-0.5| küçük = en öğretici) + kameralar arası tur atlama.
    label_queue.json'a DOKUNMAZ — sadece öneri listesi yazar.
    """
    import cv2
    from . import dogrulayici as dog

    cikti = cikti or KUYRUK_JSON
    surum = surum or ayar.ETIKET_SURUM
    if yaz:
        rapor.baslik("KUYRUK — etiketlenecek kareleri aktif öğrenmeyle sırala")
    E = rapor.joku(EGIT_JSON, None)
    if not E:
        raise SystemExit("egit.json yok — önce `egit` çalıştır")
    M = E["model"]
    HM = np.array(M["mean"], np.float32)
    HS = np.array(M["scale"], np.float32)
    HC = np.array(M["coef"], np.float32)
    HB = float(M["intercept"])

    def skorla(F):
        return 1.0 / (1.0 + np.exp(-(((F - HM) / HS) @ HC + HB)))

    lab = etiket.yukle(surum)
    q = etiket.kuyruk(surum)
    etiketli_yol = {k["rel"] for k in E["kayit"]}
    G = _npz_oku(GOMU_ETIKET)
    GT = _npz_oku(GOMU_TARA, "yol")
    GK = _npz_oku(GOMU_KUYRUK) if not yeniden else {}

    aday, eksik = [], []
    for fid, it in q.items():
        if fid in lab:
            continue
        box = it.get("pbox") or it.get("kutu")
        p = etiket.yerel_yol(it["p"])
        vec = None
        if fid in G:
            vec = G[fid]
        elif fid in GK:
            vec = GK[fid]
        elif p in GT:
            vec = GT[p]
        elif box and os.path.exists(p):
            eksik.append((fid, p, box))
        aday.append({"fid": fid, "rel": arsiv.rel(p), "cam": it.get("cam"),
                     "kaynak": "kuyruk", "det": it.get("pskor"),
                     "dog": None if vec is None else float(skorla(vec[None])[0])})
    n_kuyruk = len(aday)

    if eksik:
        if hizli:
            eksik = eksik[:max(20, ornek // 5)]
        if yaz:
            rapor.log("kuyruk gömüsü eksik: %d -> hesaplanıyor" % len(eksik))
        d = dog.Dogrulayici()
        t0 = time.time()
        yer = {it["fid"]: it for it in aday}
        for i, (fid, p, box) in enumerate(eksik, 1):
            img = cv2.imread(p)
            v = d.gomu(img, box) if img is not None else None
            if v is not None:
                GK[fid] = v
                yer[fid]["dog"] = float(skorla(v[None])[0])
            if i % 100 == 0:
                _npz_yaz(GOMU_KUYRUK, GK)
            if yaz:
                rapor.ilerleme(i, len(eksik), t0)
        _npz_yaz(GOMU_KUYRUK, GK)

    # ARŞİVDE kuyruğa hiç girmemiş kutulu kareler — "daha çok tespit" buradan gelir
    T = rapor.joku(TARA_JSON, None)
    if T:
        for r in T["kayit"]:
            if r["rel"] in etiketli_yol or r["p"] not in GT:
                continue
            aday.append({"fid": "a_" + re.sub(r"[^a-z0-9]", "", r["rel"].lower())[-30:],
                         "rel": r["rel"], "cam": r["cam"], "kaynak": "arsiv",
                         "det": r["det"], "dog": float(skorla(GT[r["p"]][None])[0])})
    if yaz:
        rapor.log("aday: %d (kuyrukta etiketsiz %d · arşivden yeni %d)"
                  % (len(aday), n_kuyruk, len(aday) - n_kuyruk))

    def belirsiz(it):
        v = it.get("dog")
        return 1.0 if v is None else abs(v - 0.5)

    kova = collections.defaultdict(list)
    for it in aday:
        kova[it["cam"]].append(it)
    for c in kova:
        kova[c].sort(key=belirsiz)
    sirali, i, kalan = [], 0, True
    while kalan:
        kalan = False
        for c in sorted(kova, key=lambda x: (x is None, x)):
            if i < len(kova[c]):
                sirali.append(kova[c][i])
                kalan = True
        i += 1
    for k, it in enumerate(sirali):
        it["i"] = k
    rapor.jyaz(cikti, {"n": len(sirali), "uretim": "sera.egitim.kuyruk", "items": sirali})

    if yaz:
        rapor.sayac([it["cam"] for it in sirali], "kamera dağılımı")
        ilk = [it["dog"] for it in sirali[:40] if it.get("dog") is not None]
        if ilk:
            rapor.log("ilk 40'ın doğrulayıcı skoru: medyan %.3f (0.5'e yakın = en öğretici)"
                      % float(np.median(ilk)))
        rapor.log("İLK 10:")
        rapor.tablo([{"k": it["cam"], "det": it["det"],
                      "dog": ("%.3f" % it["dog"]) if it.get("dog") is not None else "-",
                      "kare": it["rel"]} for it in sirali[:10]])
        rapor.log("NOT: label_queue.json'a DOKUNULMADI. Kuyruğa eklemek isteyen "
                  "append_queue.py / add_prod_box.py ile bu listeyi kullanır; karar Alperen'in.")
    ozet_m = "%d aday sıralandı" % len(sirali)
    if yaz:
        rapor.ozet("kuyruk", ozet_m, cikti)
    rapor.durum_yaz("kuyruk", ozet_m)
    return {"n": len(sirali), "items": sirali, "cikti": cikti, "ozet": ozet_m}


def ozet(yaz=True):
    """Eğitim hattının dosya durumu (durum raporu için)."""
    d = {}
    for ad, p in (("tara", TARA_JSON), ("gomu_etiket", GOMU_ETIKET),
                  ("gomu_tara", GOMU_TARA), ("egit", EGIT_JSON),
                  ("kuyruk", KUYRUK_JSON), ("aday_kafa", KAFA_ADAY)):
        var, yas_, mb = rapor.dosya_yasi(p)
        d[ad] = {"yol": p, "var": var, "yas": yas_, "mb": round(mb, 1)}
        if yaz:
            rapor.log("  %-12s %s  %-14s %6.1f MB  %s"
                      % (ad, "OK " if var else "YOK", yas_, mb, p))
    return d


if __name__ == "__main__":
    import sys
    ozet()
    if len(sys.argv) > 1:
        {"tara": tara, "gomu": gomu, "egit": egit, "disaver": disaver,
         "kuyruk": kuyruk}[sys.argv[1]]()

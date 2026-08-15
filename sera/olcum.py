# -*- coding: utf-8 -*-
"""
sera.olcum — DÜRÜST ÖLÇÜM. GroupKFold/OOF · eşleştirilmiş çalışma noktası ·
permütasyon (negatif) kontrolü · kamera-dışla · gece/gündüz kırılımı · eşik türetme.

BU MODÜLÜN VAROLUŞ SEBEBİ İKİ DERS:
  1. ÖLÇÜM TOTOLOJİSİ [[feedback_measurement_tautology]] — "0 FP / 667" sahteydi: test
     hatayı ÜRETEBİLECEK biçimde kurulmamıştı. Burada her skor FOLD-DIŞI: bir kaydın
     skoru, o kaydın SAHNESİNİ hiç görmemiş bir modelden gelir (grup = sera.arsiv.sahne).
  2. SABİT EŞİKTE/AUC İLE KIYAS [[feedback_eslestirilmis_calisma_noktasi]] — sınıf dengesi
     eşiği kaydırır. "Daha iyi" iddiası KAÇIRMAYI SABİTLE→YANLIŞA BAK (ve tersi) ile kurulur.
     Bu proje bir kez sabit eşikte kıyas yüzünden yanlış hüküm üretti (pseudo-label).

DEVRALINAN MANTIK (yeniden yazılmadı, taşındı):
  · oof()                 ← oof_esik.py:main() GroupKFold döngüsü · oof_sweep.py
  · oof_ab()              ← train_verifier3.py:main() A/B tek-değişkenli fold döngüsü
  · calisma_noktasi()     ← train_verifier3.py:108
  · eslestirilmis()       ← train_verifier3.py:117
  · nokta() / izgara()    ← sera_pipeline.py:_nokta() / adim_olc() ızgarası
  · kamera_disla()        ← train_verifier3.py:222-234 · sera_pipeline.py:588-597
  · kirilim()             ← sera_pipeline.py:adim_olc():auc_alt()
  · esik_turet()          ← oof_esik.py:main() kuyruk analizi (yanlış eşiği)
  · hacim_projeksiyonu()  ← sera_pipeline.py:_hacim_projeksiyonu()
  · ogrenme_egrisi()      ← learning_curve.py:main() "kaç etiket yeter" alt-örneklem eğrisi

EKLENEN (eskide YOKTU): permutasyon() — negatif kontrol. Etiketler karıştırıldığında
AUC 0.5'e düşmüyorsa hat sızdırıyordur; ölçüm KIRMIZI basar.
"""
import os
import time
import collections

import numpy as np

from . import ayar
from . import rapor

# ---------------------------------------------------------------- sabitler
C_LOJ = ayar.C_LOJ
MAX_ITER = ayar.MAX_ITER
SINIF_AGIRLIK = ayar.SINIF_AGIRLIK
KFOLD = ayar.KFOLD
DET_ATES = ayar.DET_ATES
DOG_ESIK = ayar.DOG_ESIK

HAT = os.path.join(ayar.GATE, "pipeline")
EGIT_JSON = os.path.join(HAT, "egit.json")
OLC_JSON = os.path.join(HAT, "olc.json")
TARA_JSON = os.path.join(HAT, "tara.json")
GOMU_TARA = os.path.join(HAT, "gomu_tara.npz")
OOF_ESIK_JSON = ayar.OOF_ESIK_JSON

# oof_sweep.py ızgarasının ÜST KÜMESİ (o noktalar aynen içinde) — sera_pipeline.py:74
IZGARA_DET = (0.52, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15, 0.10)
IZGARA_DOG = (None, 0.35, 0.40, 0.50, 0.60, 0.70, 0.85)

# permütasyon kontrolü — kaç karıştırma, kaçından iyi olmalı
PERM_N = int(ayar._oku("PERM_N", 20))
PERM_TOHUM = int(ayar._oku("PERM_TOHUM", 20260802))
# negatif kontrolün geçme ölçütü: karıştırılmış AUC ortalaması bu bandın içinde kalmalı
PERM_BANT = float(ayar._oku("PERM_BANT", 0.60))

POZ_KUTU = ("var", "cok")            # kutu gerçekten insan mı
POZ_KARE = ("var", "cok", "kutu")    # karede insan VAR mı (kutu kaymış olabilir)

# öğrenme eğrisi — learning_curve.py:main'deki oran listesi ve tekrar sayısı birebir
ORANLAR = (0.25, 0.40, 0.55, 0.70, 0.85, 1.0)
EGRI_TEKRAR = int(ayar._oku("EGRI_TEKRAR", 6))


# ============================================================ çekirdek: OOF
def _fold_egit(Ftr, ytr):
    """Tek fold eğitimi. train_verifier3.py:198-200 / sera_pipeline.py:egit_fold — birebir."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(Ftr)
    clf = LogisticRegression(C=C_LOJ, max_iter=MAX_ITER, class_weight=SINIF_AGIRLIK)
    clf.fit(sc.transform(Ftr), ytr)
    return sc, clf


def bolmeler(F, y, gruplar, n_fold=None):
    """GroupKFold bölmeleri. Grup = sera.arsiv.sahne → aynı sahne eğitim ve testte olamaz."""
    from sklearn.model_selection import GroupKFold
    g = np.asarray(gruplar)
    n = min(n_fold or KFOLD, len(set(g.tolist())))
    if n < 2:
        raise ValueError("GroupKFold icin en az 2 sahne grubu gerekli (var: %d)"
                         % len(set(g.tolist())))
    return list(GroupKFold(n_splits=n).split(F, y, groups=g))


def oof(F, y, gruplar, n_fold=None, egitilebilir=None, bolme=None):
    """FOLD-DIŞI skor. Her örneğin skoru, sahnesini görmemiş modelden gelir.

    egitilebilir : eğitimde kullanılacak örnek maskesi (None → hepsi). 'kutu' gibi
                   etiketler SKORLANIR ama EĞİTMEZ — sera_pipeline.py:619-631 davranışı.
    bolme        : hazır fold listesi (A/B kıyasında AYNI bölmeler kullanılsın diye).
    Dönüş: (oof_skor (nan olabilir), bolme)
    """
    F = np.asarray(F, np.float32)
    y = np.asarray(y).astype(int)
    if bolme is None:
        bolme = bolmeler(F, y, gruplar, n_fold)
    if egitilebilir is None:
        egitilebilir = np.ones(len(y), bool)
    egitilebilir = np.asarray(egitilebilir, bool)
    s = np.full(len(y), np.nan, np.float32)
    for tr, te in bolme:
        tr = tr[egitilebilir[tr]]
        if len(tr) < 20 or len(set(y[tr].tolist())) < 2:
            continue
        sc, clf = _fold_egit(F[tr], y[tr])
        s[te] = clf.predict_proba(sc.transform(F[te]))[:, 1]
    return s, bolme


def oof_ab(F, y, gruplar, a_maske, n_fold=None):
    """TEK DEĞİŞKENLİ A/B: aynı fold, aynı test dilimi, tek fark eğitim kümesi.

    train_verifier3.py:194-203 birebir. A = eğitim dilimi a_maske ile daraltılmış
    ("eski model ne biliyordu"), B = tüm eğitim dilimi. Ortak skorlanan test kümesi döner.
    """
    F = np.asarray(F, np.float32)
    y = np.asarray(y).astype(int)
    a_maske = np.asarray(a_maske, bool)
    bolme = bolmeler(F, y, gruplar, n_fold)
    oof_a = np.full(len(y), np.nan, np.float32)
    oof_b = np.full(len(y), np.nan, np.float32)
    for tr, te in bolme:
        for secim, hedef in ((tr[a_maske[tr]], oof_a), (tr, oof_b)):
            if len(secim) < 20 or len(set(y[secim].tolist())) < 2:
                continue
            sc, clf = _fold_egit(F[secim], y[secim])
            hedef[te] = clf.predict_proba(sc.transform(F[te]))[:, 1]
    ok = ~(np.isnan(oof_a) | np.isnan(oof_b))     # iki tarafın da skorladığı ortak küme
    return oof_a, oof_b, ok


# ============================================================ eşleştirilmiş nokta
def calisma_noktasi(y, skor):
    """Her eşik için (eşik, kaçırma, yanlış_geçen). train_verifier3.py:108 birebir."""
    y = np.asarray(y).astype(int)
    skor = np.asarray(skor, np.float32)
    out = []
    for t in np.unique(np.round(skor, 4)):
        gec = skor >= t
        out.append((float(t), int(((y == 1) & ~gec).sum()), int(((y == 0) & gec).sum())))
    return out


def eslestirilmis(y, sk_a, sk_b, ad_a="a", ad_b="b"):
    """A ve B'yi AYNI kaçırmada ve AYNI yanlış-geçende kıyasla. train_verifier3.py:117 birebir.

    kazanc > 0  →  B (yeni) daha iyi.
    """
    ca, cb = calisma_noktasi(y, sk_a), calisma_noktasi(y, sk_b)
    satir = []
    for hedef in (0, 2, 4, 6, 8, 10):
        fa = [c for c in ca if c[1] <= hedef]
        fb = [c for c in cb if c[1] <= hedef]
        if not fa or not fb:
            continue
        ya, yb = min(x[2] for x in fa), min(x[2] for x in fb)
        satir.append({"sabit": "kaçırma<=%d" % hedef, ad_a: ya, ad_b: yb, "kazanc": ya - yb})
    for hedef in (0, 3, 6, 10, 15, 20):
        fa = [c for c in ca if c[2] <= hedef]
        fb = [c for c in cb if c[2] <= hedef]
        if not fa or not fb:
            continue
        ka, kb = min(x[1] for x in fa), min(x[1] for x in fb)
        satir.append({"sabit": "yanlış<=%d" % hedef, ad_a: ka, ad_b: kb, "kazanc": ka - kb})
    return satir


def canli_nokta(y, skor, esik=None):
    """CANLI çalışma noktasında (varsayılan 0.50) kaçırma/yanlış-geçen.
    train_verifier3.py:208-212 — asıl karar burada verilir, teorik ızgarada değil."""
    esik = DOG_ESIK if esik is None else esik
    y = np.asarray(y).astype(int)
    gec = np.asarray(skor, np.float32) >= esik
    return {"esik": float(esik),
            "kacirma": int(((y == 1) & ~gec).sum()),
            "yanlis_gecen": int(((y == 0) & gec).sum()),
            "yakalanan": int(((y == 1) & gec).sum()),
            "n_poz": int((y == 1).sum()), "n_neg": int((y == 0).sum())}


# ============================================================ negatif kontrol
def permutasyon(F, y, gruplar, n=None, tohum=None, n_fold=None, sessiz=False):
    """NEGATİF KONTROL: etiketleri karıştır, aynı hattı çalıştır, AUC'ye bak.

    Eskiden bu YOKTU. Bir hat sızdırıyorsa (aynı sahne hem eğitimde hem testte, ya da
    özellik etiketten türetilmişse) karıştırılmış etiketlerle bile yüksek AUC çıkar.
    Sağlıklı hatta karıştırılmış AUC 0.5 civarındadır.

    Dönüş: {"gercek_auc","perm_ortalama","perm_maks","perm_std","p","n","gecti","sebep"}
    GEÇME ÖLÇÜTÜ: perm_ortalama <= PERM_BANT (0.60)  VE  gerçek AUC bütün permütasyonlardan
    büyük (p = (1+üstünde olan)/(1+n) <= 0.05 mertebesi).
    """
    from sklearn.metrics import roc_auc_score
    n = PERM_N if n is None else n
    tohum = PERM_TOHUM if tohum is None else tohum
    F = np.asarray(F, np.float32)
    y = np.asarray(y).astype(int)
    bolme = bolmeler(F, y, gruplar, n_fold)

    s, _ = oof(F, y, gruplar, bolme=bolme)
    ok = ~np.isnan(s)
    if len(set(y[ok].tolist())) < 2:
        return {"gecti": False, "sebep": "tek sınıf — kontrol kurulamadı", "n": 0}
    gercek = float(roc_auc_score(y[ok], s[ok]))

    rng = np.random.RandomState(tohum)
    perm = []
    t0 = time.time()
    for i in range(n):
        yk = rng.permutation(y)
        sk, _ = oof(F, yk, gruplar, bolme=bolme)
        o2 = ~np.isnan(sk)
        if len(set(yk[o2].tolist())) < 2:
            continue
        perm.append(float(roc_auc_score(yk[o2], sk[o2])))
        if not sessiz:
            rapor.ilerleme(i + 1, n, t0, "· karıştırılmış AUC %.3f" % perm[-1], adim_sayisi=10)
    if not perm:
        return {"gecti": False, "sebep": "permütasyon kurulamadı", "n": 0}
    perm = np.array(perm)
    ustunde = int((perm >= gercek).sum())
    p = (1.0 + ustunde) / (1.0 + len(perm))
    ort = float(perm.mean())
    gecti = bool(ort <= PERM_BANT and ustunde == 0)
    sebep = ""
    if ort > PERM_BANT:
        sebep = ("karıştırılmış etiketle AUC %.3f — hat SIZDIRIYOR "
                 "(sağlıklıda ~0.50 beklenir)" % ort)
    elif ustunde:
        sebep = "%d/%d karıştırma gerçek AUC'yi geçti" % (ustunde, len(perm))
    return {"gercek_auc": gercek, "perm_ortalama": ort, "perm_maks": float(perm.max()),
            "perm_min": float(perm.min()), "perm_std": float(perm.std()),
            "p": float(p), "n": int(len(perm)), "gecti": gecti, "sebep": sebep,
            "bant": PERM_BANT}


# ============================================================ kırılımlar
def kamera_disla(F, y, cam, en_az=8):
    """KAMERA-DIŞLA genelleme: bir kamerayı komple dışarıda bırak, ötekilerle eğit.

    train_verifier3.py:222-234 birebir. Sahne bölmesi aynı kameranın başka saatini
    eğitime sokabilir; bu ölçüm onu da keser — "yeni bir kameraya taşırsak ne olur".
    """
    from sklearn.metrics import roc_auc_score
    F = np.asarray(F, np.float32)
    y = np.asarray(y).astype(int)
    cam = np.asarray(cam)
    out = {}
    for c in sorted([x for x in set(cam.tolist()) if x is not None]):
        te = cam == c
        tr = ~te
        if te.sum() < en_az or len(set(y[tr].tolist())) < 2 or len(set(y[te].tolist())) < 2:
            continue
        sc, clf = _fold_egit(F[tr], y[tr])
        p = clf.predict_proba(sc.transform(F[te]))[:, 1]
        out["kamera%s" % c] = {"auc": float(roc_auc_score(y[te], p)),
                               "n": int(te.sum()), "poz": int(y[te].sum())}
    return out


def ogrenme_egrisi(F, y, gruplar, cam, oranlar=ORANLAR, tekrar=EGRI_TEKRAR,
                   det=None, det_ates=None, en_az=8, yaz=True):
    """KAÇ ETİKET YETER? — tahmin değil ÖLÇÜM. learning_curve.py:main birebir taşındı.

    Eğitim setini SAHNE bazında alt-örnekleyip kamera-dışla AUC'yi ölçer. Eğri
    düzleştiği yerde "daha fazla etiket az kazandırır" demektir — etiketleme turuna
    girmeden ÖNCE bakılacak tek sayı budur.

    ⚠ Alt-örneklem SAHNE bazında yapılır, kare bazında DEĞİL: aynı sahnenin yarısını
      eğitime yarısını teste koymak sızıntıdır ve eğriyi olduğundan düz gösterir.
    ⚠ Kıyas kamera-dışla AUC ile; her oranda `tekrar` kez farklı tohumla ölçülüp
      ortalama ± sapma verilir (tek çekiliş gürültüyü marifet sanır).

    det verilirse (üretim dedektörünün kare skoru) ateşlenebilir dilimde
    "sıfır gerçek kayıpla kesilebilen yanlış oranı" da raporlanır — learning_curve.py'nin
    `fp` sütunu. det_ates None → ayar.DET_ATES (0.52).

    ⚠ TEK BİLİNÇLİ SAPMA: learning_curve.py kafayı `max_iter=3000` ile eğitiyordu,
      burada paketin kanonik `_fold_egit`i (ayar.MAX_ITER=2000) kullanılıyor. C=0.05,
      class_weight="balanced" ve StandardScaler aynı. max_iter yakınsama tavanıdır,
      çözümü değiştirmez; ama sayı birebir tutmazsa sebebi budur —
      SERA_MAX_ITER=3000 ile eski koşu yeniden üretilir.

    -> [{"oran","n_sahne","auc_ort","auc_sapma","kesilen_fp","tekrar"}]
    """
    from sklearn.metrics import roc_auc_score
    F = np.asarray(F, np.float32)
    y = np.asarray(y).astype(int)
    g = np.asarray(gruplar)
    cam = np.asarray(cam)
    ps = None if det is None else np.asarray(det, np.float32)
    DA = DET_ATES if det_ates is None else float(det_ates)

    def _olc(maske):
        """Verilen eğitim maskesiyle kamera-dışla OOF skoru üret. learning_curve.py:olc."""
        oof = np.full(len(y), np.nan)
        for c in np.unique(cam):
            te = cam == c
            tr = (~te) & maske
            if te.sum() < en_az or tr.sum() < 20:
                continue
            if len(set(y[tr].tolist())) < 2 or len(set(y[te].tolist())) < 2:
                continue
            sc, clf = _fold_egit(F[tr], y[tr])
            oof[te] = clf.predict_proba(sc.transform(F[te]))[:, 1]
        ok = ~np.isnan(oof)
        if ok.sum() < 30 or len(set(y[ok].tolist())) < 2:
            return None, None
        auc = float(roc_auc_score(y[ok], oof[ok]))
        fp = None
        if ps is not None:
            m = ok & (ps >= DA)
            if m.sum() > 10 and 0 < y[m].sum() < m.sum():
                poz_s = oof[m][y[m] == 1]
                neg_s = oof[m][y[m] == 0]
                # gerçek insanların EN DÜŞÜĞÜNÜN altında kalan yanlış oranı = sıfır kayıpla kesilen
                fp = float((neg_s < poz_s.min()).mean())
        return auc, fp

    sahneler = np.array(sorted(set(g.tolist())))
    if yaz:
        rapor.log("ÖĞRENME EĞRİSİ — sahne bazlı alt-örneklem, %d tekrar (learning_curve.py)"
                  % tekrar)
    satir = []
    for oran in oranlar:
        aucs, fps = [], []
        n_tekrar = tekrar if oran < 1.0 else 1
        for r in range(n_tekrar):
            if oran < 1.0:
                rs = np.random.RandomState(r)
                sec = set(rs.choice(sahneler, max(3, int(len(sahneler) * oran)),
                                    replace=False).tolist())
            else:
                sec = set(sahneler.tolist())
            a, f = _olc(np.array([x in sec for x in g]))
            if a is not None:
                aucs.append(a)
            if f is not None:
                fps.append(f)
        if not aucs:
            continue
        satir.append({"oran": float(oran), "n_sahne": int(max(3, int(len(sahneler) * oran))),
                      "auc_ort": float(np.mean(aucs)), "auc_sapma": float(np.std(aucs)),
                      "kesilen_fp": float(np.mean(fps)) if fps else None,
                      "tekrar": n_tekrar})
    if yaz and satir:
        rapor.tablo([{"eğitim oranı": "%.0f%%" % (100 * s["oran"]),
                      "sahne": s["n_sahne"],
                      "AUC": "%.3f ± %.3f" % (s["auc_ort"], s["auc_sapma"]),
                      "sıfır-kayıpla kesilen yanlış":
                          ("%.0f%%" % (100 * s["kesilen_fp"])) if s["kesilen_fp"] is not None
                          else "-"} for s in satir])
        if len(satir) >= 2:
            son, onceki = satir[-1], satir[-2]
            d = son["auc_ort"] - onceki["auc_ort"]
            rapor.log("son adımın kazancı: %+.4f AUC  → %s"
                      % (d, "eğri DÜZLEŞTİ, yeni etiket az kazandırır" if abs(d) < 0.005
                         else "eğri hâlâ yükseliyor, etiketlemeye devam"))
    return satir


def kirilim(kayitlar, poz=POZ_KARE, skor_alani="oof", en_az=12, yaz=True):
    """Alt kümelerde AUC: hepsi · kamera · gece/gündüz · HD/alt-akış.
    sera_pipeline.py:adim_olc():auc_alt() — n<12 ya da tek sınıfsa "ölçülemedi" der, uydurmaz."""
    from sklearn.metrics import roc_auc_score
    poz = set(poz)

    def _auc(alt, ad):
        y = [1 if k["et"] in poz else 0 for k in alt]
        if len(set(y)) < 2 or len(alt) < en_az:
            if yaz:
                rapor.log("   %-22s n=%-4d  AUC ölçülemedi (tek sınıf ya da n<%d)"
                          % (ad, len(alt), en_az))
            return None
        s = float(roc_auc_score(y, [k[skor_alani] for k in alt]))
        if yaz:
            rapor.log("   %-22s n=%-4d poz=%-4d AUC %.4f" % (ad, len(alt), sum(y), s))
        return s

    K = [k for k in kayitlar if k.get(skor_alani) is not None]
    kir = {"hepsi": _auc(K, "hepsi")}
    for c in sorted({k["cam"] for k in K if k.get("cam")}):
        kir["kamera%s" % c] = _auc([k for k in K if k["cam"] == c], "kamera%s" % c)
    kir["GECE (20-06)"] = _auc([k for k in K if k.get("gece") is True], "GECE (20-06)")
    kir["GÜNDÜZ"] = _auc([k for k in K if k.get("gece") is False], "GÜNDÜZ")
    kir["HD kare"] = _auc([k for k in K if k.get("hd")], "HD kare")
    kir["alt akış"] = _auc([k for k in K if not k.get("hd")], "alt akış")
    return kir


# ============================================================ ızgara
def nokta(K, dt, vt, poz_set, esik_cam=None, esik_g=None):
    """Bir çalışma noktasında (yakalanan, kaçan, yanlış_geçen, negatif). sera_pipeline.py:_nokta."""
    esik_cam = esik_cam or {}
    esik_g = DOG_ESIK if esik_g is None else esik_g
    tp = fn = fp = tn = 0
    for k in K:
        p = k["et"] in poz_set
        e = (esik_cam.get("kamera%s" % k["cam"], esik_g) if vt is None else vt)
        ates = k["det"] >= dt and k["oof"] >= e
        if p:
            tp += ates
            fn += (not ates)
        else:
            fp += ates
            tn += (not ates)
    return tp, fn, fp, tn


def izgara(K, poz_set, esik_cam=None, esik_g=None, det_izgara=IZGARA_DET, dog_izgara=IZGARA_DOG):
    """det × dog ızgarasında tüm noktalar. sera_pipeline.py:adim_olc()."""
    nP = sum(1 for k in K if k["et"] in poz_set)
    nN = len(K) - nP
    out = []
    for dt in det_izgara:
        for vt in dog_izgara:
            tp, fn, fp, tn = nokta(K, dt, vt, poz_set, esik_cam, esik_g)
            out.append({"det": dt, "dog": vt, "yakalanan": tp, "kacan": fn,
                        "yanlis": fp, "n_poz": nP, "n_neg": nN})
    return out


def izgara_oneri(izg, det_ates=None):
    """Referans (bugünkü nokta) + iki EŞLEŞTİRİLMİŞ öneri.
       a) kaçan sabit → en az yanlış   b) yanlış sabit → en çok yakalayan."""
    det_ates = DET_ATES if det_ates is None else det_ates
    ref = None
    for r in izg:
        if abs(r["det"] - det_ates) < 1e-9 and r["dog"] is None:
            ref = r
            break
    if ref is None:
        ref = izg[0]
    ayni_kacan = [r for r in izg if r["kacan"] <= ref["kacan"]]
    ayni_yanlis = [r for r in izg if r["yanlis"] <= ref["yanlis"]]
    return {
        "referans": ref,
        "kacan_sabit": (min(ayni_kacan, key=lambda r: (r["yanlis"], -r["yakalanan"]))
                        if ayni_kacan else None),
        "yanlis_sabit": (max(ayni_yanlis, key=lambda r: (r["yakalanan"], -r["yanlis"]))
                         if ayni_yanlis else None),
    }


# ============================================================ eşik türetme
def esik_turet(F=None, y=None, gruplar=None, cam=None, kayitlar=None, yaz=True, cikti=None):
    """'YANLIŞ' EŞİĞİNİ FOLD-DIŞI SKORLARDAN TÜRET — oof_esik.py:main() birebir.

    Kafadan sayı yazmak yasak; eğitim skorlarına bakmak tautoloji. Gerçek pozitiflerin
    OOF dağılımının alt kuyruğu, "bunun altında gerçek insan bulunmaz" diyebileceğimiz yer.
    ⚠ Gerçek insanların %5'i 0.26'nın ALTINDA — "makul görünen" 0.10 gerçek tespit silerdi.

    kayitlar verilirse (et/cam/grup alanlı) F ile hizalı kabul edilir ve üretim varyantı
    ("cok HARIC" → poz=var, neg=yok) uygulanır.
    """
    from sklearn.metrics import roc_auc_score
    cikti = cikti or OOF_ESIK_JSON
    if kayitlar is not None:
        et = np.array([k["et"] for k in kayitlar])
        m = np.isin(et, ["var", "yok"])          # ÜRETİM VARYANTI: cok HARIC
        y = (et[m] == "var").astype(int)
        F = np.asarray(F, np.float32)[m]
        gruplar = np.array([k["grup"] for k in kayitlar])[m]
        cam = np.array([k.get("cam") for k in kayitlar])[m]
    s, _ = oof(F, y, gruplar)
    ok = ~np.isnan(s)
    y, s = np.asarray(y).astype(int)[ok], s[ok]
    cam = np.asarray(cam)[ok] if cam is not None else np.array([None] * len(y))
    auc = float(roc_auc_score(y, s))

    poz, neg = s[y == 1], s[y == 0]
    q01 = float(np.quantile(poz, 0.01))
    q02 = float(np.quantile(poz, 0.02))
    q05 = float(np.quantile(poz, 0.05))
    # TEMKİNLİ: bir olayı silmek geri dönüşsüz; kaçırmaktan pahalı (oof_esik.py:74)
    yanlis_esik = float(min(q01, 0.05))
    kesilen = int((poz < yanlis_esik).sum())
    yakalanan = int((neg < yanlis_esik).sum())

    kir = {}
    for c in sorted([x for x in set(cam.tolist()) if x is not None]):
        sel = cam == c
        if sel.sum() < 10:
            continue
        pz = s[sel & (y == 1)]
        kir["kamera%s" % c] = {"n": int(sel.sum()), "poz": int((sel & (y == 1)).sum()),
                               "poz_min": float(pz.min()) if len(pz) else None,
                               "poz_q05": float(np.quantile(pz, 0.05)) if len(pz) >= 10 else None}

    d = {"yanlis_esik": yanlis_esik, "gercek_esik": DOG_ESIK,
         "poz": {"n": int(len(poz)), "min": float(poz.min()), "q01": q01, "q02": q02,
                 "q05": q05, "medyan": float(np.median(poz))},
         "neg": {"n": int(len(neg)), "medyan": float(np.median(neg)),
                 "q98": float(np.quantile(neg, 0.98)), "maks": float(neg.max())},
         "kesim": {"kesilen_gercek": kesilen, "yakalanan_yanlis": yakalanan},
         "kamera": kir, "auc": auc, "test_olu": bool(yakalanan == 0)}
    if yaz:
        rapor.log("OOF AUC %.4f  (n=%d, poz=%d)" % (auc, len(y), int(y.sum())))
        rapor.log("GERÇEK İNSAN (n=%d): min %.4f · %%1 %.4f · %%5 %.4f · medyan %.4f"
                  % (len(poz), poz.min(), q01, q05, np.median(poz)))
        rapor.log("İNSAN YOK   (n=%d): medyan %.4f · %%98 %.4f · maks %.4f"
                  % (len(neg), np.median(neg), np.quantile(neg, 0.98), neg.max()))
        rapor.log("YANLIŞ EŞİĞİ %.6f  → altında kalan gerçek %d/%d (%%%.1f) · "
                  "yakalanan yanlış %d/%d (%%%.1f)"
                  % (yanlis_esik, kesilen, len(poz), 100.0 * kesilen / max(1, len(poz)),
                     yakalanan, len(neg), 100.0 * yakalanan / max(1, len(neg))))
        if d["test_olu"]:
            rapor.log(rapor.kirmizi("  ⚠ TEST ÖLÜ: eşik hiçbir negatifi yakalamıyor, "
                                    "denetim bir şey üretemez."))
    if cikti:
        rapor.jyaz(cikti, d)
    return d


# ============================================================ hacim projeksiyonu
def hacim_projeksiyonu(model, on, det_ates=None, esik_cam=None, esik_g=None,
                       tara_json=None, gomu_npz=None, yaz=True):
    """Gün başına kaç ateşleme? sera_pipeline.py:_hacim_projeksiyonu() birebir.

    ⚠ Buradaki doğrulayıcı skorları NİHAİ modelden gelir (fold-dışı DEĞİL) — bu bir
      KALİTE ölçümü değil, SAYI tahminidir. Kalite iddiası OOF tablolarında.
    """
    det_ates = DET_ATES if det_ates is None else det_ates
    esik_cam = esik_cam or {}
    esik_g = DOG_ESIK if esik_g is None else esik_g
    T = rapor.joku(tara_json or TARA_JSON, None)
    GT = _npz_oku(gomu_npz or GOMU_TARA, "yol")
    if not T or not GT:
        if yaz:
            rapor.log("hacim projeksiyonu atlandı (tara.json / gomu_tara.npz yok)")
        return None
    HM = np.array(model["mean"], np.float32)
    HS = np.array(model["scale"], np.float32)
    HC = np.array(model["coef"], np.float32)
    HB = float(model["intercept"])
    kay = [r for r in T["kayit"] if r["p"] in GT]
    if not kay:
        return None
    F = np.array([GT[r["p"]] for r in kay], np.float32)
    dog = 1.0 / (1.0 + np.exp(-(((F - HM) / HS) @ HC + HB)))
    gunler = sorted({r["gun"] for r in kay})
    tE = tY = 0
    sat = []
    for g in gunler:
        idx = [i for i, r in enumerate(kay) if r["gun"] == g]
        e = sum(1 for i in idx if kay[i]["det"] >= det_ates
                and dog[i] >= esik_cam.get("kamera%s" % kay[i]["cam"], esik_g))
        yy = sum(1 for i in idx if kay[i]["det"] >= on["det"]
                 and dog[i] >= (esik_cam.get("kamera%s" % kay[i]["cam"], esik_g)
                                if on["dog"] is None else on["dog"]))
        tE += e
        tY += yy
        sat.append({"gun": g, "bugun": e, "oneri": yy})
    if yaz:
        rapor.alt("HACİM PROJEKSİYONU — gün başına ateşleme (%d kutulu kare, %d gün)"
                  % (len(kay), len(gunler)))
        rapor.log("  ⚠ skorlar nihai modelden (OOF değil): kalite değil SAYI tahmini")
        rapor.tablo([r for r in sat if r["bugun"] or r["oneri"]],
                    ["gun", "bugun", "oneri"])
        n = max(1, len(gunler))
        rapor.log("  TOPLAM bugün %d · öneri %d  (%+d)   ·  gün başı %.1f -> %.1f"
                  % (tE, tY, tY - tE, tE / n, tY / n))
    return {"gunler": sat, "bugun_toplam": tE, "oneri_toplam": tY, "gun": len(gunler),
            "n_kare": len(kay)}


def _npz_oku(yol, anahtar="fid"):
    if not os.path.exists(yol):
        return {}
    z = np.load(yol, allow_pickle=True)
    return {str(k): v for k, v in zip(z[anahtar], z["F"])}


# ============================================================ ANA: olc()
def olc(egit_json=None, kafa_json=None, permutasyon_n=None, cikti=None,
        hacim=True, yaz=True):
    """DÜRÜST DEĞERLENDİRME. SADECE fold-dışı skorları okur; MODEL ÇAĞIRMAZ, EĞİTMEZ.

    Bu ayrım kasıtlı: eğitim `sera.egitim.egit()` içinde biter ve OOF skorları dosyaya
    yazar; burada aynı veriyle eğitip test etmek FİZİKSEL OLARAK mümkün değil.

    Dönüş: {"gecti": bool, "sebepler": [...], ...} — `gecti=False` ise CLI 2 ile çıkar.
    """
    from sklearn.metrics import roc_auc_score
    egit_json = egit_json or EGIT_JSON
    cikti = cikti or OLC_JSON
    E = rapor.joku(egit_json, None)
    if not E:
        raise SystemExit("egit.json yok (%s) — önce `egit` çalıştır" % egit_json)

    K = [k for k in E["kayit"] if k.get("oof") is not None]
    if yaz:
        rapor.baslik("OLC — dürüst değerlendirme (SADECE fold-dışı skorlar)")
        rapor.log("kaynak: %s" % egit_json)
        rapor.log("fold-dışı skorlanan kayıt: %d · varyant %s · etiket seti %s"
                  % (len(K), E.get("varyant"), E.get("etiket_surum", "?")))
        rapor.log("⚠ Bu tablodaki HİÇBİR skor, o kaydın sahnesini görmüş bir modelden gelmiyor.")

    h = rapor.joku(kafa_json or ayar.KAFA, {}) or {}
    esik_cam = h.get("esik_cam") or {}
    esik_g = float(h.get("esik_guvenli") or DOG_ESIK)
    if yaz:
        rapor.log("bugünkü üretim noktası: det>=%.2f · doğrulayıcı>=%.2f %s"
                  % (DET_ATES, esik_g, ("(kamera özel: %s)" % esik_cam) if esik_cam else ""))

    # ---------- kırılımlar ----------
    if yaz:
        rapor.alt("KIRILIM — kare düzeyi (insan VAR mı)")
    kir = kirilim(K, POZ_KARE, yaz=yaz)

    # ---------- ızgara + eşleştirilmiş kıyas ----------
    tablolar, oneriler = {}, {}
    for ad, poz_set in (("KARE düzeyi (insan VAR mı)", set(POZ_KARE)),
                        ("KUTU düzeyi (kutu insan mı)", set(POZ_KUTU))):
        izg = izgara(K, poz_set, esik_cam, esik_g)
        on = izgara_oneri(izg)
        ref = on["referans"]
        nP, nN = ref["n_poz"], ref["n_neg"]
        if yaz:
            rapor.alt("%s   poz=%d neg=%d   [FOLD-DIŞI]" % (ad, nP, nN))
            rapor.log(" REFERANS (bugün) det>=%.2f dog=kamera-eşiği : yakalanan %d/%d (%%%.1f) · "
                      "yanlış %d/%d" % (DET_ATES, ref["yakalanan"], nP,
                                        100.0 * ref["yakalanan"] / max(1, nP), ref["yanlis"], nN))
            rapor.log(" EŞLEŞTİRİLMİŞ KIYAS — 'daha iyi' iddiası sabit eşikte/AUC ile kurulmaz:")
            if on["kacan_sabit"]:
                a = on["kacan_sabit"]
                rapor.log("  a) KAÇAN sabit (<=%d): det>=%.2f dog>=%s -> yanlış %d (bugün %d) fark %+d"
                          % (ref["kacan"], a["det"],
                             "cam" if a["dog"] is None else "%.2f" % a["dog"],
                             a["yanlis"], ref["yanlis"], a["yanlis"] - ref["yanlis"]))
            if on["yanlis_sabit"]:
                b = on["yanlis_sabit"]
                rapor.log("  b) YANLIŞ sabit (<=%d): det>=%.2f dog>=%s -> yakalanan %d/%d "
                          "(bugün %d) fark %+d"
                          % (ref["yanlis"], b["det"],
                             "cam" if b["dog"] is None else "%.2f" % b["dog"],
                             b["yakalanan"], nP, ref["yakalanan"],
                             b["yakalanan"] - ref["yakalanan"]))
            sat = []
            for r in izg:
                if r["dog"] not in (None, 0.35, 0.50, 0.70):
                    continue
                sat.append({"det≥": "%.2f" % r["det"],
                            "dog≥": "cam" if r["dog"] is None else "%.2f" % r["dog"],
                            "yakalanan": "%d/%d" % (r["yakalanan"], nP),
                            "%": "%.1f" % (100.0 * r["yakalanan"] / max(1, nP)),
                            "kaçan": r["kacan"],
                            "yanlış": "%d/%d" % (r["yanlis"], nN),
                            "": "<- BUGÜN" if r is ref else ""})
            rapor.tablo(sat)
        tablolar[ad] = izg
        oneriler[ad] = on

    on = oneriler["KARE düzeyi (insan VAR mı)"]["yanlis_sabit"]
    ref = oneriler["KARE düzeyi (insan VAR mı)"]["referans"]

    # ---------- NEGATİF KONTROL ----------
    perm = None
    sebepler = []
    Fg = _gomu_egitten(E)
    if Fg is not None:
        et = np.array([k["et"] for k in E["kayit"]])
        grp = np.array([k["grup"] for k in E["kayit"]])
        m = np.isin(et, list(set(POZ_KUTU) | {"yok"}))
        y = np.isin(et, list(POZ_KUTU)).astype(int)[m]
        if yaz:
            rapor.alt("NEGATİF KONTROL — etiketleri karıştır, AUC 0.5'e düşmeli")
        try:
            perm = permutasyon(Fg[m], y, grp[m], n=permutasyon_n, sessiz=not yaz)
        except Exception as e:
            perm = {"gecti": False, "sebep": "kontrol çalıştırılamadı: %s" % str(e)[:120]}
        if yaz:
            if perm.get("n"):
                rapor.log("  gerçek AUC %.4f · karıştırılmış AUC ort %.4f (min %.3f, maks %.3f, "
                          "n=%d) · p=%.3f"
                          % (perm["gercek_auc"], perm["perm_ortalama"], perm["perm_min"],
                             perm["perm_maks"], perm["n"], perm["p"]))
            rapor.log("  " + (rapor.yesil("KONTROL GEÇTİ — hat sızdırmıyor")
                              if perm.get("gecti")
                              else rapor.kirmizi("KONTROL GEÇMEDİ: " + perm.get("sebep", "?"))))
        if not perm.get("gecti"):
            sebepler.append("permütasyon (negatif) kontrolü geçmedi: %s" % perm.get("sebep", "?"))
    else:
        sebepler.append("gömü bulunamadı — permütasyon kontrolü ÇALIŞTIRILAMADI "
                        "(ölçüm doğrulanmamış sayılır)")
        if yaz:
            rapor.alt("NEGATİF KONTROL")
            rapor.log("  " + rapor.kirmizi("gömü yok → kontrol çalıştırılamadı"))

    # ---------- akıl sağlığı: kırılımda ölçülemeyen çok mu ----------
    olculemeyen = [k for k, v in kir.items() if v is None]
    if kir.get("hepsi") is None:
        sebepler.append("genel AUC ölçülemedi (tek sınıf ya da n<12)")

    # ---------- öneri ----------
    if yaz:
        rapor.log()
        rapor.log("=" * 74, zaman=False)
        rapor.log(rapor.kalin("ÖNERİLEN ÇALIŞMA NOKTASI "
                              "(yanlış alarm bugünün üstüne ÇIKMADAN en çok tespit)"), zaman=False)
        rapor.log("   det >= %.2f   doğrulayıcı >= %s"
                  % (on["det"], "kamera" if on["dog"] is None else "%.2f" % on["dog"]))
        rapor.log("   yakalanan %d -> %d  (+%d)   ·   yanlış-geçen %d -> %d"
                  % (ref["yakalanan"], on["yakalanan"], on["yakalanan"] - ref["yakalanan"],
                     ref["yanlis"], on["yanlis"]))
        rapor.log("   ⚠ Etiket setinde ölçüldü (n=%d). Telefon ORAN'la değil SAYI ile öter."
                  % len(K))
        rapor.log("=" * 74, zaman=False)

    hac = None
    if hacim and E.get("model"):
        hac = hacim_projeksiyonu(E["model"], on, esik_cam=esik_cam, esik_g=esik_g, yaz=yaz)

    d = {"kirilim": kir, "auc_oof": E.get("auc_oof"), "varyant": E.get("varyant"),
         "etiket_surum": E.get("etiket_surum"), "tablolar": tablolar, "oneriler": oneriler,
         "oneri": on, "hacim": hac, "n": len(K), "permutasyon": perm,
         "olculemeyen_kirilim": olculemeyen,
         "referans_esik": {"det": DET_ATES, "dog": esik_g, "esik_cam": esik_cam},
         "gecti": len(sebepler) == 0, "sebepler": sebepler}
    rapor.jyaz(cikti, d)
    rapor.durum_yaz("olc", "OOF AUC %.4f · öneri det>=%.2f dog>=%s · yakalanan %d->%d, "
                           "yanlış %d->%d · %s"
                    % (E.get("auc_oof") or 0.0, on["det"],
                       "cam" if on["dog"] is None else "%.2f" % on["dog"],
                       ref["yakalanan"], on["yakalanan"], ref["yanlis"], on["yanlis"],
                       "GEÇTİ" if not sebepler else "GEÇMEDİ"))
    if yaz and sebepler:
        rapor.log()
        rapor.log(rapor.kirmizi("ÖLÇÜM GEÇMEDİ:"), zaman=False)
        for s in sebepler:
            rapor.log(rapor.kirmizi("  · " + s), zaman=False)
    return d


def _gomu_egitten(E):
    """egit.json'daki kayıtlarla hizalı gömü matrisi (permütasyon kontrolü için)."""
    yollar = [os.path.join(HAT, "gomu_etiket.npz"), ayar.GOMU_946, ayar.GOMU_763]
    onbellek = {}
    for p in yollar:
        if p and os.path.exists(p):
            z = np.load(p, allow_pickle=True)
            for f, v in zip(list(z["fid"]), z["F"]):
                onbellek.setdefault(str(f), v)
    if not onbellek:
        return None
    eksik = [k for k in E["kayit"] if k["fid"] not in onbellek]
    if eksik:
        return None                      # hizalanamıyorsa SESSİZCE eksik matris üretme
    return np.stack([onbellek[k["fid"]] for k in E["kayit"]]).astype(np.float32)


def ozet(yaz=True):
    """Son ölçümün tek satırlık hâli (durum raporu için)."""
    O = rapor.joku(OLC_JSON, None)
    if not O:
        return None
    on, ref = O.get("oneri") or {}, (O.get("oneriler") or {}).get(
        "KARE düzeyi (insan VAR mı)", {}).get("referans", {})
    d = {"auc_oof": O.get("auc_oof"), "n": O.get("n"), "varyant": O.get("varyant"),
         "gecti": O.get("gecti"), "sebepler": O.get("sebepler") or [],
         "oneri_det": on.get("det"), "oneri_dog": on.get("dog"),
         "yakalanan": (ref.get("yakalanan"), on.get("yakalanan")),
         "yanlis": (ref.get("yanlis"), on.get("yanlis")),
         "permutasyon": O.get("permutasyon")}
    if yaz:
        rapor.log("OOF AUC %s · n=%s · %s" % (d["auc_oof"], d["n"],
                                              "GEÇTİ" if d["gecti"] else "GEÇMEDİ"))
    return d


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "esik":
        esik_turet()
    else:
        r = olc()
        sys.exit(0 if r["gecti"] else 2)

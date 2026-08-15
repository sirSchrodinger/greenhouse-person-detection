# -*- coding: utf-8 -*-
"""
sera.dagit — DOĞRULAYICI KAFASINI VPS'E KUR ve GERİ AL (2 Ağu 2026).

Sistemin EN RİSKLİ parçası: buradaki bir hata canlı güvenlik sistemini bozar. O yüzden
tek bir kural var — HİÇBİR ŞEY `uygula=True` OLMADAN YAZILMAZ. Varsayılan her zaman kuru.

Devralınan: deploy_model.sh (yedek+scp+restart+is-active deseni) · sera_pipeline.py:890
(`HEAD_JSON + ".yedek-%d" % int(time.time())` yedek adı) · train_verifier2.py:111.
VPS'te zaten bu isimle iki yedek duruyor (verifier_head.json.yedek-1785643699 / -1785663704),
yani adlandırma uydurulmadı, var olan gelenek sürdürüldü.

═══════════════════════════════════════════════════════════════════════════════
 SSH İLE ÖLÇÜLDÜ (2 Ağu, SALT-OKUMA) — VARSAYIMLA ÇALIŞMA, `durum()` ÇAĞIR
═══════════════════════════════════════════════════════════════════════════════
 · `sera-person.service` → /opt/sera/person_watch.py  ÇALIŞTIRIYOR.
   O dosya doğrulayıcıyı HİÇ KULLANMIYOR (grep -c verifier = 0).
   YANİ: kafa değişimi sera-person'u ETKİLEMEZ; restart etmeye gerek yok.
 · `sera-person-canary.service` → /opt/sera/person_watch_v3.py, PCAMS=kamera5.
   Doğrulayıcıyı kullanan TEK AKTİF servis bu. Kafa değişimi SADECE kamera5'i etkiler.
 · `sera-person-shadow.service` → person_watch_v3.py ama INACTIVE.
 · /opt/sera/dvr_ince_hasat.py de doğrulayıcıyı kullanıyor ama bir unit'e/cron'a bağlı
   değil (elle çalıştırılıyor) → restart gerekmez, sonraki elle koşu yeni kafayı okur.
 · /opt/sera/verifier.py kafayı SÜREÇ BAŞINA BİR KEZ yükler (_yukle/_hazir) →
   dosyayı değiştirmek YETMEZ, servis restart ŞART.

 ⚠ KOD DAĞITIMI BU MODÜLÜN İŞİ DEĞİL (bu modül KAFA dağıtır). Yine de aynı ekranda
   görünsün diye `durum()` person_watch_v3.py'nin yerel/uzak md5'ini kıyaslar. Bu turda
   iki kez ölçüldü ve ARADA DEĞİŞTİ: 17:12'de VPS kopyasında doğrulayıcı KURTARMA bloğu
   (VER_KURTAR) YOKTU, 17:37'de yerelle AYNI oldu ve canary dosya güncellendikten SONRA
   restart edilmişti. "Hatırladığım gibi"ye güvenme — `durum()` çağır.

Kullanım (bu turda SADECE bunlar çalıştırıldı):
    from sera import dagit
    dagit.durum()                                   # salt-okuma
    dagit.kuru_tur(ayar.KAFA_V3)                    # ne değişecek, kim etkilenecek
    # gerçek kurulum Alperen tetikler:
    # dagit.kur(ayar.KAFA_V3, uygula=True)
    # dagit.geri_al(uygula=True)

YAZMA YÜZEYİ — bu modülde VPS'e yazan TEK ÜÇ yer var, hepsi uygula=True'nun arkasında:
    kur(uygula=True)      → cp (yedek) · scp (kafa) · systemctl restart
    geri_al(uygula=True)  → cp (yedeği geri koy) · systemctl restart
    kur()'un kurtarma dalları → yukarıdaki ikisini AÇIK uygula=True ile çağırır
durum() · kuru_tur() · uzak_kafa() · yedekler() · etkilenen_servisler() SALT OKUMADIR.
"""
import os
import json
import time
import shutil
import hashlib
import subprocess

from . import ayar

# ============================================================================ sabitler
VPS = ayar.VPS_HOST                       # <vps-host>
ANAHTAR = ayar.VPS_ANAHTAR                # ~/.ssh/id_ed25519
VPS_KOK = ayar.VPS_KOK                    # /opt/sera
UZAK_KAFA = ayar.VPS_KAFA                 # /opt/sera/models/verifier_head.json
UZAK_GOVDE = VPS_KOK.rstrip("/") + "/models/verifier_dinov2.onnx"
YEDEK_ONEK = os.path.basename(UZAK_KAFA) + ".yedek-"

# Doğrulayıcıyı kullanan servisler — VARSAYIM DEĞİL, `etkilenen_servisler()` ölçer.
# Aşağıdaki liste sadece "bakılacak yer"i söyler.
ADAY_SERVISLER = ("sera-person", "sera-person-canary", "sera-person-shadow", "sera-state")
# /opt/sera/verifier.py'yi import eden dosya adı → hangi unit'te koşuyorsa o etkilenir
DOG_KULLANAN = ("verifier",)

SSH_SECENEK = ["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
               "-o", "ConnectTimeout=12"]
BEKLE_S = 10                       # restart sonrası sağlık kontrolü öncesi bekleme
JOURNAL_SATIR = 5

# kafa JSON'unda BULUNMASI ZORUNLU alanlar — /opt/sera/verifier.py:_yukle bunları okur
ZORUNLU_ALAN = ("mean", "scale", "coef", "intercept", "esik_guvenli", "esik_agresif", "kirp")


# ==========================================================================
#  SSH / SCP  (bu turda YALNIZCA okuma çağrıldı)
# ==========================================================================
def _ssh(komut, zaman_asimi=45, kontrol=False):
    """VPS'te komut çalıştır. -> (rc, stdout, stderr).

    ⚠ BatchMode=yes: parola sorulmaz, takılıp kalmaz. Zaman aşımı ZORUNLU —
    ağ kesilirse dağıtım yarıda asılı kalmasın.
    """
    a = ["ssh", "-i", ANAHTAR] + SSH_SECENEK + [VPS, komut]
    r = subprocess.run(a, capture_output=True, text=True, timeout=zaman_asimi)
    if kontrol and r.returncode != 0:
        raise RuntimeError("ssh basarisiz (rc=%s): %s" % (r.returncode, (r.stderr or "")[:200]))
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _scp(yerel, uzak, zaman_asimi=180):
    """Dosyayı VPS'e kopyala. SADECE kur() içinden, uygula=True iken çağrılır."""
    a = ["scp", "-i", ANAHTAR] + SSH_SECENEK + [yerel, "%s:%s" % (VPS, uzak)]
    r = subprocess.run(a, capture_output=True, text=True, timeout=zaman_asimi)
    if r.returncode != 0:
        raise RuntimeError("scp basarisiz: %s" % (r.stderr or "")[:200])
    return True


def _md5(yol):
    h = hashlib.md5()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


# ==========================================================================
#  OKUMA
# ==========================================================================
def kafa_oku(yol):
    """Yerel kafa JSON'u oku + zorunlu alan kontrolü. -> (veri, [eksik_alan])"""
    with open(yol) as f:
        d = json.load(f)
    eksik = [a for a in ZORUNLU_ALAN if a not in d]
    return d, eksik


def _kafa_ozeti(d):
    """Kafanın karşılaştırılabilir imzası (mean/scale/coef 768'lik, tabloya girmez)."""
    e = d.get("egitim") or {}
    return {"govde": d.get("govde"), "boyut": d.get("boyut") or len(d.get("coef") or []),
            "intercept": d.get("intercept"),
            "esik_guvenli": d.get("esik_guvenli"), "esik_agresif": d.get("esik_agresif"),
            "esik_cam": d.get("esik_cam") or {}, "kirp": d.get("kirp"),
            "surum": e.get("surum"), "n": e.get("n"), "poz": e.get("poz"), "neg": e.get("neg"),
            "varyant": e.get("varyant"),
            # ⚠ auc_cv ile auc_oof AYNI SAYI DEĞİL (biri katlar-içi CV, öbürü fold-dışı).
            #   Hangi anahtardan geldiği taşınır ki kıyas "0.99 -> 0.98 gerilemiş" gibi
            #   SAHTE bir sonuç üretmesin. Kıyas EŞLEŞTİRİLMİŞ olmalı.
            "auc": e.get("auc_oof") if e.get("auc_oof") is not None else e.get("auc_cv"),
            "auc_tur": "oof" if e.get("auc_oof") is not None else (
                "cv" if e.get("auc_cv") is not None else None)}


def uzak_kafa(yol=None):
    """VPS'teki kafanın özeti + md5 + boyut. SALT OKUMA."""
    p = yol or UZAK_KAFA
    rc, out, err = _ssh(
        "python3 -c \"import json,hashlib,os;p='%s';"
        "d=json.load(open(p));"
        "h=hashlib.md5(open(p,'rb').read()).hexdigest();"
        "print(json.dumps({'md5':h,'boyut':os.path.getsize(p),'mtime':os.path.getmtime(p),"
        "'kafa':{k:v for k,v in d.items() if k not in ('mean','scale','coef')}}))\"" % p)
    if rc != 0:
        return {"var": False, "hata": err[:200], "yol": p}
    try:
        d = json.loads(out)
    except Exception:
        return {"var": False, "hata": "uzak JSON cozulemedi: " + out[:160], "yol": p}
    k = d["kafa"]
    k["coef"] = None
    return {"var": True, "yol": p, "md5": d["md5"], "boyut": d["boyut"], "mtime": d["mtime"],
            "ozet": _kafa_ozeti(k)}


def yedekler(yaz=False):
    """VPS'teki zaman damgalı kafa yedekleri (yeni → eski). SALT OKUMA."""
    rc, out, _e = _ssh("ls -1t %s.yedek-* 2>/dev/null" % UZAK_KAFA)
    lst = [x for x in out.splitlines() if x.strip()] if rc == 0 else []
    r = []
    for p in lst:
        dmg = p.rsplit(".yedek-", 1)[-1]
        r.append({"yol": p, "damga": dmg,
                  "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(dmg)))
                  if dmg.isdigit() else "?"})
    if yaz:
        for x in r:
            print("   %s  %s" % (x["zaman"], x["yol"]))
    return r


def etkilenen_servisler(yaz=False):
    """DOĞRULAYICIYI GERÇEKTEN KULLANAN aktif servisleri ÖLÇ (varsayma).

    Her aday unit'in ExecStart'ındaki .py dosyasında `verifier` geçiyor mu diye bakar.
    Bu, "sera-person'u da restart et" gibi gereksiz (ve riskli) işlemleri önler:
    ölçüldü, sera-person eski person_watch.py'yi koşuyor ve doğrulayıcıyı kullanmıyor.
    -> [{"servis","durum","script","dogrulayici","restart_gerek"}]
    """
    kod = (
        "for s in %s; do "
        "  f=$(systemctl show -p FragmentPath --value $s 2>/dev/null); "
        "  a=$(systemctl is-active $s 2>/dev/null); "
        "  py=$(grep -h '^ExecStart' \"$f\" 2>/dev/null | grep -o '/opt/sera/[A-Za-z0-9_]*\\.py' | head -1); "
        "  v=0; [ -n \"$py\" ] && [ -f \"$py\" ] && v=$(grep -c verifier \"$py\" 2>/dev/null || echo 0); "
        "  echo \"$s|$a|$py|$v\"; "
        "done" % " ".join(ADAY_SERVISLER))
    rc, out, err = _ssh(kod)
    if rc != 0:
        return [{"servis": "?", "hata": err[:160]}]
    r = []
    for satir in out.splitlines():
        pr = satir.split("|")
        if len(pr) < 4:
            continue
        s, a, py, v = pr[0], pr[1], pr[2], pr[3]
        try:
            n = int(v.strip() or 0)
        except ValueError:
            n = 0
        r.append({"servis": s, "durum": a, "script": py or None, "dogrulayici": n > 0,
                  "restart_gerek": bool(n > 0 and a == "active")})
    if yaz:
        for x in r:
            print("   %-24s %-9s dogrulayici=%-5s restart=%-5s %s"
                  % (x["servis"], x["durum"], x["dogrulayici"], x["restart_gerek"],
                     x["script"] or ""))
    return r


def durum(yaz=True):
    """VPS'in dağıtımla ilgili tam resmi. SALT OKUMA — hiçbir şeye dokunmaz.

    -> {"erisim","kafa","yedek","servis","kod_farki"}
    """
    d = {}
    rc, out, err = _ssh("hostname; uptime -p")
    d["erisim"] = {"ok": rc == 0, "cikti": out, "hata": err[:160] if rc else None}
    if rc != 0:
        if yaz:
            print("VPS'e ERISILEMEDI: %s" % err[:200])
        return d
    d["kafa"] = uzak_kafa()
    d["yedek"] = yedekler()
    d["servis"] = etkilenen_servisler()

    # kod farkı: kafa dağıtımını ilgilendirmez ama aynı ekranda görünsün (bkz. modül başlığı)
    yerel_pw = os.path.join(ayar.VPS_KOD, "person_watch_v3.py")
    kf = {"yerel": yerel_pw, "yerel_var": os.path.exists(yerel_pw)}
    if kf["yerel_var"]:
        rc2, out2, _ = _ssh("md5sum %s/person_watch_v3.py 2>/dev/null | cut -d' ' -f1; "
                            "grep -c VER_KURTAR %s/person_watch_v3.py 2>/dev/null || echo 0"
                            % (VPS_KOK, VPS_KOK))
        pr = out2.split()
        kf["uzak_md5"] = pr[0] if pr else None
        kf["uzak_ver_kurtar"] = int(pr[1]) if len(pr) > 1 and pr[1].isdigit() else None
        kf["yerel_md5"] = _md5(yerel_pw)
        # ⚠ grep -c SATIR sayar, str.count GEÇİŞ sayar. İkisi karıştırılırsa "yerel 14 /
        #   uzak 13" gibi SAHTE bir fark çıkar (VER_KURTAR_ESIK aynı satırda ikinci geçiş).
        #   Elmayla elma: burada da satır sayılır.
        with open(yerel_pw, "rb") as f:
            kf["yerel_ver_kurtar"] = sum(1 for s in f if b"VER_KURTAR" in s)
        kf["ayni"] = (kf["yerel_md5"] == kf["uzak_md5"])
    d["kod_farki"] = kf

    if yaz:
        print("=" * 78)
        print("VPS DURUMU — %s   (%s)" % (VPS, out.replace("\n", " · ")))
        print("=" * 78)
        k = d["kafa"]
        if k.get("var"):
            o = k["ozet"]
            print("KAFA   : %s" % k["yol"])
            print("         md5 %s · %d B · %s"
                  % (k["md5"][:12], k["boyut"],
                     time.strftime("%Y-%m-%d %H:%M", time.localtime(k["mtime"]))))
            print("         surum=%s n=%s (poz %s/neg %s) varyant=%s auc=%s"
                  % (o["surum"], o["n"], o["poz"], o["neg"], o["varyant"], o["auc"]))
            print("         esik_guvenli=%s esik_agresif=%s kirp=%s"
                  % (o["esik_guvenli"], o["esik_agresif"], o["kirp"]))
        else:
            print("KAFA   : OKUNAMADI — %s" % k.get("hata"))
        print("YEDEK  : %d adet" % len(d["yedek"]))
        for x in d["yedek"][:5]:
            print("         %s  %s" % (x["zaman"], os.path.basename(x["yol"])))
        print("SERVIS :")
        for x in d["servis"]:
            print("         %-24s %-9s dogrulayici=%-5s restart_gerek=%-5s %s"
                  % (x.get("servis"), x.get("durum"), x.get("dogrulayici"),
                     x.get("restart_gerek"), x.get("script") or ""))
        if kf.get("yerel_var"):
            print("KOD    : person_watch_v3.py  yerel %s / uzak %s  -> %s"
                  % (kf["yerel_md5"][:12], (kf.get("uzak_md5") or "?")[:12],
                     "AYNI" if kf.get("ayni") else "FARKLI"))
            print("         VER_KURTAR (dogrulayici kurtarma bloğu): yerel %s · uzak %s%s"
                  % (kf.get("yerel_ver_kurtar"), kf.get("uzak_ver_kurtar"),
                     "   ⚠ CANLIDA YOK" if not kf.get("uzak_ver_kurtar") else ""))
        print("=" * 78)
    return d


# ==========================================================================
#  KURU TUR
# ==========================================================================
def kuru_tur(yerel_kafa=None, yaz=True):
    """Neyin değişeceğini göster: dosya farkı + etkilenen servis. HİÇBİR ŞEY YAZMAZ.

    -> {"yerel","uzak","fark","servis","engel","hazir"}
    """
    p = yerel_kafa or ayar.kafa_yolu(v3=True)
    r = {"yerel_yol": p, "engel": [], "hazir": False}

    if not os.path.exists(p):
        r["engel"].append("yerel kafa yok: %s" % p)
        if yaz:
            print("ENGEL: yerel kafa yok: %s" % p)
        return r
    try:
        d, eksik = kafa_oku(p)
    except Exception as e:
        r["engel"].append("yerel kafa JSON cozulemedi: %s" % str(e)[:120])
        if yaz:
            print("ENGEL: %s" % r["engel"][-1])
        return r
    if eksik:
        r["engel"].append("kafada ZORUNLU alan eksik: %s (verifier.py yukleyemez)" % eksik)
    # kırpma tutarlılığı: kafa hangi kırpmayla eğitildiyse çıkarımda AYNISI olmalı
    k = d.get("kirp") or {}
    simdi = {"W": ayar.KIRP_W, "H": ayar.KIRP_H, "PAD": ayar.PAD, "giris": ayar.GIRIS}
    kirp_fark = {a: (k.get(a), simdi[a]) for a in simdi
                 if k.get(a) is not None and k.get(a) != simdi[a]}
    if kirp_fark:
        r["engel"].append("KIRPMA SAPMASI %s — skorlar anlamsiz olur" % kirp_fark)

    r["yerel"] = {"ozet": _kafa_ozeti(d), "md5": _md5(p), "boyut": os.path.getsize(p)}
    u = uzak_kafa()
    r["uzak"] = u
    r["servis"] = etkilenen_servisler()
    r["yedek"] = yedekler()

    fark = {}
    if u.get("var"):
        a, b = u["ozet"], r["yerel"]["ozet"]
        for alan in ("surum", "n", "poz", "neg", "varyant", "auc", "esik_guvenli",
                     "esik_agresif", "boyut", "intercept", "govde"):
            if a.get(alan) != b.get(alan):
                fark[alan] = {"vps": a.get(alan), "yeni": b.get(alan)}
        fark["_ayni_dosya"] = (u.get("md5") == r["yerel"]["md5"])
        fark["_auc_kiyaslanamaz"] = (a.get("auc_tur") != b.get("auc_tur"))
    r["fark"] = fark
    r["hazir"] = bool(not r["engel"] and u.get("var") and not fark.get("_ayni_dosya"))

    if yaz:
        print("=" * 78)
        print("KURU TUR — DOĞRULAYICI KAFASI DAĞITIMI (hiçbir şey yazılmadı)")
        print("=" * 78)
        print("YEREL  : %s" % p)
        print("         md5 %s · %d B" % (r["yerel"]["md5"][:12], r["yerel"]["boyut"]))
        b = r["yerel"]["ozet"]
        print("         surum=%s n=%s (poz %s/neg %s) auc=%s esik=%s/%s"
              % (b["surum"], b["n"], b["poz"], b["neg"], b["auc"],
                 b["esik_guvenli"], b["esik_agresif"]))
        if u.get("var"):
            a = u["ozet"]
            print("VPS    : %s" % u["yol"])
            print("         md5 %s · %d B" % (u["md5"][:12], u["boyut"]))
            print("         surum=%s n=%s (poz %s/neg %s) auc=%s esik=%s/%s"
                  % (a["surum"], a["n"], a["poz"], a["neg"], a["auc"],
                     a["esik_guvenli"], a["esik_agresif"]))
        else:
            print("VPS    : OKUNAMADI — %s" % u.get("hata"))
        print("\nFARK   :")
        if not fark:
            print("         (okunamadi)")
        elif fark.get("_ayni_dosya"):
            print("         AYNI DOSYA (md5 esit) — dagitmaya gerek yok")
        else:
            for alan, v in fark.items():
                if alan.startswith("_"):
                    continue
                print("         %-14s VPS %-24s -> YENI %s" % (alan, v["vps"], v["yeni"]))
            if fark.get("_auc_kiyaslanamaz"):
                print("         ⚠ AUC KIYASLANAMAZ: VPS '%s', yeni '%s' — farklı ölçüler."
                      % (u["ozet"].get("auc_tur"), b.get("auc_tur")))
                print("           Kıyas EŞLEŞTİRİLMİŞ ÇALIŞMA NOKTASINDA yapılır; iki AUC'yi"
                      "\n           yan yana koyup 'gerilemiş/iyileşmiş' DEME.")
        print("\nETKİLENEN SERVİS (ölçüldü, varsayılmadı):")
        for x in r["servis"]:
            im = "RESTART EDİLECEK" if x.get("restart_gerek") else (
                "dokunulmayacak (doğrulayıcı kullanmıyor)" if not x.get("dogrulayici")
                else "pasif, dokunulmayacak")
            print("         %-24s %-9s %s" % (x.get("servis"), x.get("durum"), im))
        rst = [x["servis"] for x in r["servis"] if x.get("restart_gerek")]
        print("\nADIMLAR (uygula=True verilirse):")
        print("   1. VPS'te %s -> %s<epoch>" % (os.path.basename(UZAK_KAFA), YEDEK_ONEK))
        print("   2. scp %s -> %s" % (os.path.basename(p), UZAK_KAFA))
        print("   3. systemctl restart %s ; %d sn bekle" % (" ".join(rst) or "(yok)", BEKLE_S))
        print("   4. is-active + journalctl son %d satır" % JOURNAL_SATIR)
        print("   5. sağlık bozuksa OTOMATİK GERİ AL (yedeği koy, tekrar restart)")
        if r["engel"]:
            print("\nENGEL (%d) — kur() bunlarla ÇALIŞMAZ:" % len(r["engel"]))
            for e in r["engel"]:
                print("   · %s" % e)
        print("\nSONUÇ  : %s" % ("dağıtıma HAZIR (uygula=True bekliyor)" if r["hazir"]
                                 else "dağıtılmayacak"))
        print("=" * 78)
    return r


# ==========================================================================
#  KURULUM
# ==========================================================================
def _saglik(servisler, yaz=True):
    """Restart sonrası sağlık: is-active + journalctl son satırlar + hata izi.

    -> {"ok": bool, "servis": {ad: {"aktif","log","hata"}}}
    """
    r = {"ok": True, "servis": {}}
    for s in servisler:
        _rc, aktif, _e = _ssh("systemctl is-active %s" % s)
        _rc2, log, _e2 = _ssh("journalctl -u %s -n %d -o cat --no-pager"
                              % (s, JOURNAL_SATIR))
        alt = (log or "").lower()
        # verifier.py kafa yükleyemezse bunu loglar; "traceback" da yeterli sinyal
        hata = any(x in alt for x in ("traceback", "keyerror", "jsondecodeerror",
                                      "no such file", "dogrulayici kapali",
                                      "doğrulayıcı kapalı", "verifier yuklenemedi"))
        r["servis"][s] = {"aktif": aktif, "log": log, "hata": hata}
        if aktif != "active" or hata:
            r["ok"] = False
        if yaz:
            print("   %-24s %-9s %s" % (s, aktif, "⚠ LOGDA HATA İZİ" if hata else ""))
            for satir in (log or "").splitlines():
                print("        | %s" % satir)
    return r


def kur(yerel_kafa=None, uygula=False, servisler=None, yaz=True):
    """Yeni doğrulayıcı kafasını VPS'e kur. KURU VARSAYILAN.

    uygula=True akışı (ve yalnız o zaman yazma yapılır):
      1. VPS'teki mevcut kafanın ZAMAN DAMGALI yedeğini al
      2. yeni kafayı kopyala (scp)
      3. doğrulayıcı kullanan AKTİF servisleri restart et, BEKLE_S(10) sn bekle
      4. is-active + journalctl son JOURNAL_SATIR(5) satır kontrol
      5. sağlık bozuksa OTOMATİK GERİ AL ve hata döndür

    ⚠ Kuru turda ENGEL varsa (eksik alan, kırpma sapması, VPS okunamıyor) kur() çalışmaz.
    ⚠ Restart edilecek servis listesi ÖLÇÜLÜR (etkilenen_servisler); "hepsini restart et"
      yaklaşımı bilerek yok — doğrulayıcı kullanmayan sera-person'u gereksiz yere
      düşürmek canlı güvenlik sisteminde kabul edilebilir bir risk değil.
    """
    p = yerel_kafa or ayar.kafa_yolu(v3=True)
    kt = kuru_tur(p, yaz=yaz)
    if not uygula:
        if yaz:
            print("\nKURULMADI (kuru tur). Kurmak için: kur(..., uygula=True)")
        return dict(kt, uygulandi=False)
    if kt["engel"]:
        return dict(kt, uygulandi=False, hata="engel var: %s" % kt["engel"])
    if not kt.get("uzak", {}).get("var"):
        return dict(kt, uygulandi=False, hata="VPS kafasi okunamadi — dagitim yok")
    if kt["fark"].get("_ayni_dosya"):
        return dict(kt, uygulandi=False, hata="ayni dosya — dagitmaya gerek yok")

    rst = servisler if servisler is not None else [
        x["servis"] for x in kt["servis"] if x.get("restart_gerek")]

    dmg = int(time.time())
    yedek = "%s.yedek-%d" % (UZAK_KAFA, dmg)
    if yaz:
        print("\n1) YEDEK: %s" % yedek)
    rc, _o, e = _ssh("cp -p %s %s && ls -l %s" % (UZAK_KAFA, yedek, yedek))
    if rc != 0:
        return dict(kt, uygulandi=False, hata="yedek alinamadi: %s" % e[:160])

    if yaz:
        print("2) KOPYA: %s -> %s" % (p, UZAK_KAFA))
    try:
        _scp(p, UZAK_KAFA)
    except Exception as ex:
        _ssh("cp -p %s %s" % (yedek, UZAK_KAFA))          # kopya yarıda kaldıysa geri koy
        return dict(kt, uygulandi=False, yedek=yedek,
                    hata="scp basarisiz, kafa geri konuldu: %s" % str(ex)[:160])

    # kopya gerçekten oturdu mu? (md5 eşleşmesi — "kopyalandı" demeden önce KANIT)
    rc, out, _e = _ssh("md5sum %s | cut -d' ' -f1" % UZAK_KAFA)
    if rc != 0 or out.strip() != kt["yerel"]["md5"]:
        _ssh("cp -p %s %s" % (yedek, UZAK_KAFA))
        return dict(kt, uygulandi=False, yedek=yedek,
                    hata="md5 tutmadi (uzak %s / yerel %s) — geri konuldu"
                         % (out.strip()[:12], kt["yerel"]["md5"][:12]))

    if yaz:
        print("3) RESTART: %s  (+%d sn bekle)" % (" ".join(rst) or "(yok)", BEKLE_S))
    if rst:
        rc, _o, e = _ssh("systemctl restart %s" % " ".join(rst), zaman_asimi=90)
        if rc != 0:
            # kurtarma yolu — uygula AÇIKÇA verilir (geri_al varsayılanı kurudur)
            geri_al(dmg, uygula=True, yaz=yaz, servisler=rst)
            return dict(kt, uygulandi=False, yedek=yedek,
                        hata="restart basarisiz, GERI ALINDI: %s" % e[:160])
        time.sleep(BEKLE_S)

    if yaz:
        print("4) SAĞLIK:")
    sag = _saglik(rst, yaz=yaz) if rst else {"ok": True, "servis": {}}
    if not sag["ok"]:
        if yaz:
            print("\n⚠ SAĞLIK BOZUK — OTOMATİK GERİ ALINIYOR")
        # kurtarma yolu — uygula AÇIKÇA verilir (geri_al varsayılanı kurudur)
        ga = geri_al(dmg, uygula=True, yaz=yaz, servisler=rst)
        return dict(kt, uygulandi=False, yedek=yedek, saglik=sag, geri_al=ga,
                    hata="saglik bozuk, otomatik geri alindi")

    if yaz:
        print("\nKURULDU. yedek: %s   (geri almak icin: geri_al(%d))" % (yedek, dmg))
    return dict(kt, uygulandi=True, yedek=yedek, damga=dmg, saglik=sag,
                restart=rst)


def geri_al(damga=None, uygula=False, servisler=None, yaz=True):
    """Son (ya da verilen) yedeğe dön + restart. KURU VARSAYILAN.

    damga=None → VPS'teki EN YENİ yedek. uygula=False → sadece ne yapılacağını yazar.

    ⚠ 2 Ağu düzeltmesi: bu fonksiyonun varsayılanı `uygula=True` İDİ. Yani
      `dagit.geri_al()` — argümansız, bir REPL'de yanlışlıkla — canlı VPS'te
      verifier_head.json'u ezip sera-person-canary'yi restart ediyordu. Modülün
      "hiçbir şey uygula=True olmadan yazılmaz" kuralının TEK istisnasıydı ve
      kural yazının kendisiydi. Varsayılan kuruya çevrildi; kur()'un otomatik
      kurtarma yolu artık uygula=True'yu AÇIKÇA veriyor (davranış aynı kaldı).
    """
    yd = yedekler()
    if not yd:
        if yaz:
            print("GERİ ALINACAK YEDEK YOK (%s.yedek-*)" % UZAK_KAFA)
        return {"ok": False, "hata": "yedek yok"}
    if damga is None:
        hedef = yd[0]["yol"]
    else:
        hedef = "%s.yedek-%s" % (UZAK_KAFA, damga)
        if hedef not in [x["yol"] for x in yd]:
            return {"ok": False, "hata": "yedek bulunamadi: %s" % hedef}

    rst = servisler if servisler is not None else [
        x["servis"] for x in etkilenen_servisler() if x.get("restart_gerek")]
    if yaz:
        print("GERİ AL: %s -> %s   (restart: %s)"
              % (hedef, UZAK_KAFA, " ".join(rst) or "(yok)"))
    if not uygula:
        print("  (uygula=False — hiçbir şey yapılmadı)")
        return {"ok": False, "kuru": True, "hedef": hedef, "restart": rst}

    rc, _o, e = _ssh("cp -p %s %s" % (hedef, UZAK_KAFA))
    if rc != 0:
        return {"ok": False, "hata": "geri kopyalama basarisiz: %s" % e[:160]}
    if rst:
        _ssh("systemctl restart %s" % " ".join(rst), zaman_asimi=90)
        time.sleep(BEKLE_S)
    sag = _saglik(rst, yaz=yaz) if rst else {"ok": True, "servis": {}}
    if yaz:
        print("GERİ ALINDI: %s  (saglik %s)" % (hedef, "OK" if sag["ok"] else "BOZUK"))
    return {"ok": sag["ok"], "hedef": hedef, "restart": rst, "saglik": sag}


# ==========================================================================
#  YEREL YEDEK  (kafayı yerelde değiştirmeden önce)
# ==========================================================================
def yerel_yedek(yol=None):
    """Yerel kafayı zaman damgalı yedekle. BİREBİR sera_pipeline.py:890 deseni."""
    p = yol or ayar.KAFA
    y = "%s.yedek-%d" % (p, int(time.time()))
    shutil.copy(p, y)
    return y


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] == "durum":
        durum()
    elif a[0] == "kuru":
        kuru_tur(a[1] if len(a) > 1 else None)
    elif a[0] == "yedek":
        yedekler(yaz=True)
    else:
        print(__doc__)

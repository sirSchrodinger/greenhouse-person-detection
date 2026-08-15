# -*- coding: utf-8 -*-
"""
sera — sera görü sistemi, TEK gerçek kaynak paketi (2 Ağu 2026).

64 script / ~11.000 satır boyunca kopyalanmış mantık burada tek yerde toplanır.
Kural: bu bir REFACTOR'dur — sayısal davranış değişmez. Her fonksiyonun docstring'inde
hangi eski dosyadan devralındığı yazar. Eşik/sabit değiştirmek bu paketin işi değil.

Katmanlar (bağımlılık yönü yukarıdan aşağı):
    ayar        — yollar, eşikler, sabitler (SERA_<AD> ile ezilebilir)
    gorsel      — kırpma / ImageNet normalizasyonu / kutu çizimi / kontakt sayfası
    arsiv       — kaynak gezgini, zaman damgası, kamera/gün, sahne grubu, olay kareleri
    dedektor    — YOLO11s ileri geçişi (640 alt-akış / 960 HD)
    dogrulayici — DINOv2 gömü + lojistik kafa + eşik politikası
    etiket · olcum · egitim · retro · olay · sahne · dagit · rapor

Python ortamı: <project-venv>/bin/python
(sistem python3'ünde cv2 YOK — bu tuzağa bir kez düşüldü.)

Hızlı başlangıç:
    from sera import ayar, arsiv, gorsel
    ayar.ozet(); ayar.dogrula()
    kareler = arsiv.kaynaklar()
    gorsel.kontakt([gorsel.hucre(p) for p in kareler[:10]], "/tmp/bak.jpg", sutun=5)
"""
SURUM = "1.0.0-2026-08-02"

from . import ayar  # noqa: F401  — yan etkisiz, sadece sabitler

_ALT = ("ayar", "gorsel", "arsiv", "dedektor", "dogrulayici", "etiket", "olcum",
        "egitim", "retro", "olay", "sahne", "dagit", "rapor")

__all__ = list(_ALT) + ["SURUM"]


def __getattr__(ad):
    """Tembel yükleme: `sera.gorsel` yazınca cv2 o an import edilir.
    Böylece sadece sera.ayar isteyen bir süreç cv2/onnxruntime yükünü ödemez."""
    if ad in _ALT:
        import importlib
        m = importlib.import_module("." + ad, __name__)
        globals()[ad] = m
        return m
    raise AttributeError("sera paketinde '%s' yok" % ad)

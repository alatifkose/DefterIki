"""Test oturumu ortak ayarları.

Qt pencere testleri ekransız çalışır: ``QT_QPA_PLATFORM=offscreen`` yalnız
tanımlı değilse konur, böylece geliştirici kendi ayarını verebilir.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

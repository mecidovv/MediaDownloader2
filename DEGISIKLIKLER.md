# Yapılan değişiklikler (kaynak kod üzerinden, ölçüm yapılmadan)

Tasarım (renkler, yerleşim) değiştirilmedi.

1. css/style.css + js/app.js: Çekmece (Ayarlar/Geçmiş) açıkken ve pencere arka plandayken LED çerçeve animasyonu duruyor.
   Neden: LED, her adımda tüm pencere boyutunda conic-gradient'i yeniden boyuyor; çekmecenin arkasındaki
   backdrop-filter blur(22px) de bu her adımda yeniden hesaplanıyor.
2. js/app.js: Pano izni reddedilirse/yoksa otomatik pano algılama her pencere odağında tekrar denemiyor.
3. backend/downloads.py: İndirme işçisi SQLite'ı, indirme durumunu sorgulayan isteklerin de kullandığı kilidi
   tutarken okumuyordu; artık kilit dışında okuyor (tests/test_download_locking.py bunu doğrular; eski kodda başarısız oluyor).
4. backend/api.py: Modül import edilirken ikinci bir app (Storage + DownloadManager) oluşturulmuyor; `backend.api:app` ilk erişimde oluşuyor.
5. backend/storage.py: `PRAGMA journal_mode=WAL` her bağlantıda değil, yalnızca başlangıçta çalışıyor.

Yeni testler: tests/test_download_locking.py, tests/test_performance.py içine api import testi.


## Sürüm 1.1 değişiklikleri
- Ana ekran: ortada zarif başlık, indirme ikonu ve gereksiz yazılar (güvenli bağlantı, ipuçları, yer tutucu) kaldırıldı.
- Yerel Windows pencere çubuğu kullanılıyor (özel küçült/büyüt/kapat düğmeleri kaldırıldı).
- Geçmiş ve ayar çekmeceleri kapalıyken tamamen gizli (kenardan görünme düzeltildi, `inert` + `visibility`).
- Pano Python tarafından okunuyor (`/api/v1/clipboard`); tarayıcı izin penceresi çıkmıyor.
- Dosya adı biçimi ayarı arayüzden kaldırıldı. "Harici içerik yükleme" varsayılan olarak açık (eski kurulumlar bir kez otomatik açılır).
- 7 dilli arayüz (tr, en, ru, de, it, ko, zh): `js/i18n.js` ve `js/lang-*.js`. Ayarlar > Genel > Dil.
- Hakkında: sürüm, yt-dlp/FFmpeg sürümü, güncelleme denetimi (`/api/v1/about`, `/api/v1/about/updates`), kullanım koşulları, gizlilik, lisanslar.
- İndirme bitince bildirim ve ses (ayarlara bağlı) çalışıyor.
- Yükleyici: `installer.iss` (Inno Setup 6, lisans onay sayfası, otomatik kurulum, kısayol, kaldırıcı), `build.ps1` Setup.exe üretir. Uygulama simgesi: `assets/icons/app.ico`.

# MediaDownloader

Windows için video indirici (Python, yt-dlp, FFmpeg, pywebview). Arayüz 7 dili destekler: Türkçe, English, Русский, Deutsch, Italiano, 한국어, 中文.

## Kurulum dosyasını (Setup.exe) edinme

**Yol 1: GitHub kendisi derlesin (önerilen)**
1. Bu depoyu GitHub'a yükleyin.
2. **Actions** sekmesi > **Build Windows installer** > **Run workflow**.
3. İş bitince (birkaç dakika) sayfanın altındaki **Artifacts** bölümünden `MediaDownloader-Setup` dosyasını indirin.
4. Sürüm olarak yayınlamak için bir etiket oluşturun: `git tag v1.1.0` ardından `git push origin v1.1.0`. `Setup.exe` otomatik olarak **Releases** sayfasına eklenir.

**Yol 2: Kendi bilgisayarınızda derleyin**
1. Inno Setup 6 kurun: `winget install JRSoftware.InnoSetup`
2. Proje klasöründe PowerShell açın ve `.\build.ps1` çalıştırın.
3. Sonuç: `installer_output\MediaDownloader-Setup.exe`

> `Setup.exe` gibi derlenmiş dosyaları depoya (kod olarak) değil, **Releases** bölümüne yükleyin.

Windows masaüstü video indirici. Arayüz mevcut tasarımı korur; video bilgisi ve indirme yt-dlp ile, MP3 dönüştürme FFmpeg ile yapılır.

## Hazır uygulamayı çalıştırma

1. `MediaDownloader-Windows.zip` dosyasını yeni bir klasöre çıkarın.
2. Klasördeki `MediaDownloader.exe` dosyasını çalıştırın; `_internal` klasörünü EXE'nin yanından taşımayın veya silmeyin.
3. Windows'ta WebView2 Runtime kurulu olmalıdır.

İlk açılışta dosyalar klasördeki `_internal` dizininden yüklenir. Uygulamayı kullanırken bu dizini EXE'nin yanında bırakın.

## Kaynak koddan çalıştırma

Windows'ta PowerShell'i proje klasöründe açın:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_desktop.py
```

Video bilgisi almak ve indirmek için **Ayarlar > Gelişmiş > Harici içerik yükleme** iznini açın. Ayarlar ve geçmiş bu bilgisayarda saklanır. Kaynağın erişime izin vermediği içerikler indirilemeyebilir.

## Test ve paketleme

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1
```

Paketleme `dist\MediaDownloader\MediaDownloader.exe` klasörlü uygulamayı ve kökünde EXE'nin ilk sırada, `_internal` klasörünün yanında olduğu `MediaDownloader-Windows.zip` dosyasını oluşturur. EXE tek başına taşınırsa Python DLL yüklenemez.

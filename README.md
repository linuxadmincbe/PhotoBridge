# PhotoBridge

Google Drive’daki veya bilgisayarınızdaki bir klasörde bulunan fotoğraf ve videolarınızı Google Fotoğraflar’a kopyalayan Python araçları.

| Kaynak | Çalıştırılacak dosya |
| --- | --- |
| Google Drive klasörü | `sync.py` |
| Bilgisayardaki yerel klasör | `upload_photos_fast.py` |

Aşağıdaki ilk kurulum ve Drive adımlarından sonra, bilgisayardan aktarım için ayrıca **Bilgisayardaki klasörden yükleme** bölümüne bakın.

## Ne işe yarar?

`sync.py`, seçtiğiniz Google Drive klasörünü ve alt klasörlerini tarar. Görsel ve video olarak tanınan dosyaları bilgisayarınıza indirir, ardından giriş yaptığınız Google hesabının Google Fotoğraflar kitaplığına yükler.

- Drive’daki kaynak dosyaları değiştirmez veya silmez.
- Başarıyla yüklenen dosyaların Drive kimliklerini `uploaded.log` dosyasında tutar; sonraki çalıştırmada bu kimlikleri atlar.
- Dosyaları `transfer/` klasöründe saklar. Aynı adlı dosyaların çakışmasını önlemek için yerelde Drive dosya kimliğini kullanır; Google Fotoğraflar’a asıl dosya adını gönderir.
- Yükleme yanıtını kontrol eder; başarısız dosyayı tamamlandı olarak kaydetmez.

Bu bir çift yönlü eşitleme aracı değildir. Drive klasör yapısını Google Fotoğraflar albümlerine dönüştürmez ve Fotoğraflar’daki mevcut dosyaları karşılaştırmaz. Aynı dosya farklı Drive kimliğiyle bulunuyorsa veya günlük kaybolursa yeniden yükleme olabilir.

## Gereksinimler

- Python 3.10 veya üzeri ve internet bağlantısı.
- Kaynak Drive klasörüne erişebilen ve hedef Google Fotoğraflar hesabı olarak kullanılacak Google hesabı.
- Kendi Google Cloud projeniz ve **Desktop app / Masaüstü uygulaması** türünde OAuth istemcisi.
- İndirilecek dosyalar için yeterli yerel disk alanı ve Google hesabında uygun depolama alanı.

## 1. Uygulamayı indirin ve bağımlılıkları kurun

Windows PowerShell’de:

```powershell
git clone https://github.com/linuxadmincbe/PhotoBridge.git
cd PhotoBridge
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Git kurulu değilse GitHub’daki **Code → Download ZIP** seçeneğiyle indirin, arşivi açın ve PowerShell’i açılan proje klasöründe çalıştırın. Ardından yukarıdaki son iki komutu uygulayın. `py` bulunamıyorsa Python kurulumunuzu kontrol edin; sisteminizde mevcutsa `python` komutunu kullanın.

## 2. Google erişimini hazırlayın

Aşağıdaki ayarlar iki aracı da kullanmak içindir. Yalnızca bilgisayardan yükleyecekseniz **Photos Library API** ve `photoslibrary.appendonly` izni yeterlidir; Drive API ve Drive izni gerekmez.

1. [Google Cloud Console](https://console.cloud.google.com/) üzerinde bir proje oluşturun veya kendi projenizi seçin.
2. **APIs & Services → Library** bölümünden **Google Drive API** ve **Photos Library API** hizmetlerini etkinleştirin.
3. **Google Auth Platform** bölümündeki uygulama adı, destek e-postası ve hedef kitle ayarlarını doldurun. Kişisel Gmail hesabında hedef kitle genellikle **External** olur. Uygulama **Testing** durumundaysa kullanacağınız Google hesabını test kullanıcılarına ekleyin. Menü adları arayüz diline göre değişebilir.
4. **Data Access / Veri erişimi** bölümünde şu izin kapsamlarını tanımlayın:
   - `https://www.googleapis.com/auth/drive.readonly`
   - `https://www.googleapis.com/auth/photoslibrary.appendonly`
5. **Clients / İstemciler** bölümünden **Desktop app / Masaüstü uygulaması** türünde OAuth istemcisi oluşturun.
6. İstemcinin JSON dosyasını indirin, adını `credentials.json` yapın ve `sync.py` ile aynı klasöre koyun.

Her kullanıcı kendi OAuth istemcisini oluşturmalıdır. Bu depoda gerçek kimlik veya token dosyası bulunmaz. Service account dosyası bu giriş akışının yerine geçmez.

Uygulama Drive için salt okunur erişim, Google Fotoğraflar için yeni medya ekleme izni ister. Drive izni yalnızca seçtiğiniz klasörle sınırlı bir OAuth izni değildir; kod taramayı verdiğiniz klasörden başlatır.

## 3. Kaynak Drive klasörünün kimliğini bulun

Drive’da aktaracağınız klasörü açın. Adresi şu biçimdedir:

```text
https://drive.google.com/drive/folders/KLASOR_KIMLIGI
```

`folders/` sonrasındaki klasör kimliğini alın; tam bağlantıyı komuta yapıştırmayın.

## 4. Aktarımı başlatın

Önce az sayıda dosya içeren bir klasörle deneyin:

```powershell
.\.venv\Scripts\python.exe sync.py --folder-id "KLASOR_KIMLIGI"
```

`KLASOR_KIMLIGI` yerine kendi Drive klasörünüzün kimliğini yazın.

İlk çalıştırmada tarayıcıda Google giriş ve izin ekranı açılır. Hem kaynak Drive klasörüne erişebilen hem de fotoğrafların yükleneceği hesabı seçin. Giriş tamamlandığında uygulama yerelde `token.json` oluşturur ve aktarımı başlatır. Sonuçları [Google Fotoğraflar](https://photos.google.com/) üzerinden kontrol edebilirsiniz.

Klasör kimliğini alternatif olarak yalnızca mevcut PowerShell oturumu için tanımlayabilirsiniz:

```powershell
$env:DRIVE_FOLDER_ID = "KLASOR_KIMLIGI"
.\.venv\Scripts\python.exe sync.py
```

Sonraki çalıştırmalarda aynı komutu kullanın. Süreci durdurmak için `Ctrl+C` tuşlarına basabilirsiniz. Başarı günlüğüne yazılmış dosyalar tekrar çalıştırmada atlanır. Google tarafında yükleme tamamlanıp yerel günlük yazılmadan süreç kesilirse aynı dosyanın tekrar yüklenmesi mümkündür.

## Bilgisayardaki klasörden yükleme

`upload_photos_fast.py`, bilgisayarınızda bulunan `transfer/` klasörünü alt klasörleriyle tarar ve uzantısı listede olan fotoğraf/videoları Google Fotoğraflar’a yükler. Google Drive’dan dosya indirmez. Yerel fotoğraf ve videoları silmez, taşımaz veya değiştirmez.

### Hazırlık ve çalıştırma

1. Yukarıdaki Python kurulumunu ve `requirements.txt` kurulumunu tamamlayın.
2. Google Cloud’da **Photos Library API** hizmetini etkinleştirin ve **Desktop app** OAuth istemcisinin `credentials.json` dosyasını `upload_photos_fast.py` yanına koyun. İlk girişte yalnızca `photoslibrary.appendonly` izni istenir.
3. Proje klasöründe `transfer` adlı klasör oluşturun ve yüklemek istediğiniz fotoğraf/videoları buraya koyun. Alt klasörler de taranır.
4. Proje klasöründe PowerShell açıp çalıştırın:

```powershell
.\.venv\Scripts\python.exe upload_photos_fast.py
```

İlk çalıştırmada tarayıcıdan **hedef Google Fotoğraflar hesabına** giriş yapıp izin verin. Bu araç `token_local.json` oluşturur; Drive aracının `token.json` dosyasından ayrıdır. Böylece iki aracın farklı izinleri birbirine karışmaz.

Dosyaları kopyalamak istemiyorsanız `upload_photos_fast.py` içindeki şu satırı düzenleyerek doğrudan kendi klasörünüzü seçebilirsiniz:

```python
TRANSFER_DIR = Path(r"D:\Fotograflar")
```

Bu örnek yolu kendi klasörünüzle değiştirin. Varsayılan satır `TRANSFER_DIR = BASE_DIR / "transfer"` biçimindedir. Doğrudan taranan klasördeki dosyalar da silinmez veya taşınmaz. Aktarım sırasında kaynak dosyaları değiştirmeyin.

### Hız ve kaldığı yerden devam etme

- Varsayılan olarak **4 paralel dosya yükleme** yapar (`UPLOAD_WORKERS = 4`).
- Yüklenen dosyaların Google Fotoğraflar’da oluşturulmasını en fazla **50 öğelik paketlerle** yapar (`BATCH_SIZE = 50`).
- İlerlemeyi `upload_state.db` adlı SQLite veritabanında saklar. Başarıyla tamamlanmış ve değişmemiş dosyaları sonraki çalıştırmada atlar; boyutu veya değiştirilme zamanı değişen dosyaları yeniden işleme alır.
- Bazı bağlantı ve geçici sunucu hatalarında otomatik yeniden deneme yapar. Yeniden denenen bir istekte sunucunun önceki işlemi tamamlayıp tamamlamadığı belirsizse kopya oluşması mümkündür.
- Hataları `upload_errors.log` dosyasına kaydeder. `Ctrl+C` ile durdurabilirsiniz; çalışan ağ işlemlerinin bitmesi zaman alabilir. Yeniden başlatırken aynı komutu kullanın.

Veritabanını koruyun: silinirse tamamlanan dosyalar yeniden yüklenebilir. Bu araç içerik özetiyle küresel kopya kontrolü yapmaz. Google Fotoğraflar’daki mevcut kitaplığı taramaz ve klasörleri albümlere dönüştürmez. Uzantı listesinde olması Google’ın dosyayı kabul edeceğini garanti etmez.

**Aynı proje klasöründe tek aktarım çalıştırın.** Yerel aracın veritabanı ile Drive aracının `uploaded.log` günlüğü birbirinden bağımsızdır. Drive aracının indirdiği dosyaları yerel araçla tekrar yüklerseniz kopya oluşabilir. Kaynak klasör veya hedef hesap değiştirirken önceki veritabanı ve tokenı güvenli şekilde yedekleyip ayrı bir proje kopyası kullanın. Veritabanı önceki klasöre ait bekleyen dosya yollarını da tutabilir.

`upload_state.db`, varsa `upload_state.db-wal` / `upload_state.db-shm`, `upload_errors.log` ve `token_local.json` dosyalarını GitHub’a yüklemeyin. Veritabanı kişisel dosya yolları, Google medya kimlikleri ve geçici yükleme tokenları içerebilir. Depodaki `.gitignore` bunları dışarıda bırakır.

## Yerel dosyalar ve gizlilik

| Dosya / klasör | Amaç | GitHub’a yüklenir mi? |
| --- | --- | --- |
| `sync.py` | Drive aktarım kodu | Evet |
| `upload_photos_fast.py` | Bilgisayardaki klasörden yükleme kodu | Evet |
| `requirements.txt` | Python bağımlılıkları | Evet |
| `credentials.json` | Size ait OAuth istemcisi | Hayır |
| `token.json` | Google erişim ve yenileme tokenları | Hayır |
| `token_local.json` | Yerel yükleyicinin Google tokenları | Hayır |
| `upload_state.db*` | Yerel yükleyicinin ilerleme ve yükleme tokenları | Hayır |
| `upload_errors.log` | Yerel yükleyicinin hata günlüğü | Hayır |
| `token.pickle` | Eski sürümün token dosyası | Hayır |
| `uploaded.log` | Başarıyla aktarılan Drive dosya kimlikleri | Hayır |
| `transfer/` | İndirilen kişisel fotoğraf ve videolar | Hayır |

`.gitignore` bu yerel dosyaları dışarıda bırakır. Kimlik veya token dosyalarına `git add -f` uygulamayın. `.gitignore`, daha önce Git geçmişine eklenmiş bir sırrı silmez. Bir token yanlışlıkla paylaşılırsa ilgili Google uygulama erişimini iptal edin; açığa çıkan OAuth istemci bilgilerini Google Cloud üzerinden yenileyin ve Git geçmişini ayrıca temizleyin.

`transfer/` içindeki dosyalar aktarım sonrasında otomatik silinmez. Disk alanı açmadan önce Google Fotoğraflar’daki sonucu doğrulayın. `uploaded.log` dosyasını koruyun; farklı bir hedef Google hesabına geçerken eski hesabın günlüğünü kullanırsanız dosyalar atlanır. Hesap değişiminde token ve günlük dosyalarını ayrı ve güvenli şekilde yedekleyip yeni hesap için temiz bir çalışma klasörü kullanın.

## Eski sürümden geçiş

Bu sürüm `token.pickle` dosyasını okumaz; ilk kullanımda yeniden giriş yapar ve `token.json` oluşturur. Eski başarı günlüğünüzü kullanmak istiyorsanız aynı hedef Google hesabına ait olduğundan ve dosyaların gerçekten yüklenmiş olduğundan emin olun. Eski sürüm yükleme hatalarını doğrulamadan günlük yazabildiği için kayıtların doğruluğunu kontrol edin. Eski klasörünüzdeki kimlik, token, günlük ve fotoğrafları GitHub’a yüklemeyin.

## Sık karşılaşılan durumlar

- **`credentials.json` bulunamadı:** İndirdiğiniz Desktop OAuth JSON dosyasını bu adla `sync.py` yanına yerleştirin. Windows’ta dosyanın yanlışlıkla `credentials.json.json` olmadığını kontrol edin.
- **`access_denied` / 403:** Doğru Google hesabını, test kullanıcılarını, API etkinleştirmelerini ve istenen izinleri kontrol edin. Kurumsal hesaplarda yönetici kısıtlaması olabilir.
- **`invalid_grant`:** Erişim iptal edilmiş veya yenileme tokenı süresi dolmuş olabilir. Uygulamayı durdurun, ilgili yerel token dosyasını (`sync.py` için `token.json`, yerel yükleyici için `token_local.json`) güvenli şekilde kaldırıp yeniden giriş yapın. `uploaded.log` dosyasını koruyun. External ve Testing durumundaki bu kapsamlara sahip OAuth uygulamalarında yenileme tokenı 7 gün sonra sona erebilir.
- **429 veya kota hatası:** Aktarımı durdurun, Google Cloud kotanızı kontrol edip daha sonra yeniden deneyin. Drive aracı otomatik geri çekilme yapmaz; yerel araç bazı geçici hataları yeniden dener. İki araç da arka planda zamanlama yapmaz.
- **Desteklenmeyen medya / yükleme hatası:** MIME türüne göre seçilen her dosya Google Fotoğraflar tarafından kabul edilmeyebilir. Google’ın biçim ve boyut kısıtlarını kontrol edin. Hata oluştuğunda uygulama durur; ilgili dosya başarı günlüğüne eklenmez.

Aynı çalışma klasöründen birden fazla aktarımı aynı anda başlatmayın. Dosyalar indirilmiş kopyadan yüklenir; Drive’daki sonradan yapılan değişiklikler yerel önbellekle otomatik karşılaştırılmaz. Albüm düzeninin ve Google Fotoğraflar’da görünen tarihlerin birebir korunması garanti edilmez.

## Resmî belgeler

- [Google Fotoğraflar API yapılandırması](https://developers.google.com/photos/overview/configure-your-app)
- [Google Fotoğraflar medya yükleme akışı ve kısıtları](https://developers.google.com/photos/library/guides/upload-media)
- [Masaüstü uygulamaları için Google OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [OAuth token süreleri ve iptal koşulları](https://developers.google.com/identity/protocols/oauth2/)

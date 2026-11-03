# PhotoBridge

Google Drive’daki fotoğraf ve videolarınızı Google Fotoğraflar’a kopyalayan Python uygulaması.

## Ne işe yarar?

PhotoBridge, seçtiğiniz Google Drive klasörünü ve alt klasörlerini tarar. Görsel ve video olarak tanınan dosyaları bilgisayarınıza indirir, ardından giriş yaptığınız Google hesabının Google Fotoğraflar kitaplığına yükler.

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

## Yerel dosyalar ve gizlilik

| Dosya / klasör | Amaç | GitHub’a yüklenir mi? |
| --- | --- | --- |
| `sync.py` | Uygulama kodu | Evet |
| `requirements.txt` | Python bağımlılıkları | Evet |
| `credentials.json` | Size ait OAuth istemcisi | Hayır |
| `token.json` | Google erişim ve yenileme tokenları | Hayır |
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
- **`invalid_grant`:** Erişim iptal edilmiş veya yenileme tokenı süresi dolmuş olabilir. Uygulamayı durdurun, yerel `token.json` dosyasını güvenli şekilde kaldırıp yeniden giriş yapın. `uploaded.log` dosyasını koruyun. External ve Testing durumundaki bu kapsamlara sahip OAuth uygulamalarında yenileme tokenı 7 gün sonra sona erebilir.
- **429 veya kota hatası:** Aktarımı durdurun, Google Cloud kotanızı kontrol edip daha sonra yeniden deneyin. Uygulama otomatik geri çekilme veya arka planda zamanlama yapmaz.
- **Desteklenmeyen medya / yükleme hatası:** MIME türüne göre seçilen her dosya Google Fotoğraflar tarafından kabul edilmeyebilir. Google’ın biçim ve boyut kısıtlarını kontrol edin. Hata oluştuğunda uygulama durur; ilgili dosya başarı günlüğüne eklenmez.

Aynı çalışma klasöründen birden fazla aktarımı aynı anda başlatmayın. Dosyalar indirilmiş kopyadan yüklenir; Drive’daki sonradan yapılan değişiklikler yerel önbellekle otomatik karşılaştırılmaz. Albüm düzeninin ve Google Fotoğraflar’da görünen tarihlerin birebir korunması garanti edilmez.

## Resmî belgeler

- [Google Fotoğraflar API yapılandırması](https://developers.google.com/photos/overview/configure-your-app)
- [Google Fotoğraflar medya yükleme akışı ve kısıtları](https://developers.google.com/photos/library/guides/upload-media)
- [Masaüstü uygulamaları için Google OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [OAuth token süreleri ve iptal koşulları](https://developers.google.com/identity/protocols/oauth2/)

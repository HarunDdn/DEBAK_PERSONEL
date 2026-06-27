# DEBAK_PERSONEL — CANIAS HCM Kalan İzin Servisi

CANIAS ERP (IAS Industrial Application Software, v8.03) **HCMT101** işleminin
arka planında çalışan TROIA kodlarının (trace dosyası) analiz edilerek
Python'a aktarılmış halidir. Amaç: bir web uygulamasından gönderilen
**personel numarasına (`IASHCMLVGRP.PERSID`)** göre kişinin kalan izin
günlerini (CANIAS ekranındaki `REM1`, `REM2`, `REM3`, `REM4` alanları)
hesaplayıp döndürmektir.

Trace'teki örnek personel (PERSID `1028`) için beklenen sonuç:

| Alan | İzin Grubu | İzin Adı (IASHCM306X.STEXT) | Kalan (REMLVDAYS) |
|------|------------|-----------------------------|-------------------|
| REM1 | GR08 | Diğer Ücretsiz İzin        | 3.0  |
| REM2 | GR01 | Yıllık İzin                | 20.0 |
| REM3 | GR08 | Hastalık İzni (Ödemesiz)   | 3.0  |
| REM4 | GR08 | Ücretli Mazeret İzni       | 3.0  |

---

## 1. İş Planı

1. **Trace analizi (tamamlandı):** `HARUN.DIDIN_HCMT101_*.txt` dosyasındaki
   SQL ve TROIA fonksiyonları çözümlendi. Kritik bulgu: **`REMLVDAYS`
   veritabanında saklanan bir kolon değildir; çalışma anında hesaplanır**
   (`APPEND COLUMN REMLVDAYS ... TO HCMLVGRP`). Bu yüzden tek bir SELECT
   yetmez; CANIAS'ın `SETREMLVDAYS` mantığının yeniden üretilmesi gerekir.
2. **Veri erişim katmanı:** Trace'teki SQL'lerin birebir kopyaları
   (`app/providers.py`). MSSQL'e `pyodbc` ile bağlanılır.
3. **Hesaplama motoru:** `SETREMLVDAYS` ve tüm alt fonksiyonlarının Python
   karşılığı (`app/canias_leave.py`).
4. **Web servisi:** FastAPI ile `GET /personnel/{persid}/remaining-leaves`
   (`app/main.py`).
5. **Doğrulama:** Trace değerleriyle (3 / 20 / 3 / 3) birim testleri
   (`tests/`).

---

## 2. Hesaplamanın Mantığı (trace ile birebir)

### 2.1 Ana sorgu — izin gruplarını çek
`HCMT101D001.GETREMAININGDAYS.0 28`:

```sql
SELECT IASHCMLVGRP.*, IASHCM306.LEAVECODE AS LEAVECODE, IASHCM306X.STEXT AS STEXT
FROM IASHCMLVGRP
LEFT JOIN IASHCM306  ON (IASHCMLVGRP.CLIENT = IASHCM306.CLIENT
                     AND IASHCMLVGRP.LEAVECODE = IASHCM306.LEAVECODE)
LEFT JOIN IASHCM306X ON (IASHCM306.CLIENT = IASHCM306X.CLIENT
                     AND IASHCM306.COMPANY = IASHCM306X.COMPANY
                     AND IASHCM306.LEAVECODE = IASHCM306X.LEAVECODE)
WHERE IASHCMLVGRP.CLIENT = @client   -- '00'
  AND IASHCMLVGRP.PERSID = @persid   -- '1028'
  AND IASHCM306.COMPANY  = @company  -- '01'
  AND IASHCM306X.LANGU   = @langu    -- 'T'
ORDER BY IASHCM306.LEAVECODE;
```

Dönen her satır bir izin türüdür. `REM1..REMn` bu sıraya (LEAVECODE) göre
atanır.

### 2.2 Her satır için: `SETREMLVDAYS`
Temel formül (`SETREMLVDAYS.0 58`):

```
REMLVDAYS = TOTEARNED − LVDAYS − USEDDAY
```

Adımlar:
1. `IASHCM213` (izin grubu ayarı) yoksa satır atlanır → `REMLVDAYS = 0`.
2. **`EXCLUDEDSEN = CALCEXCLUDEDSEN(...)`** — kıdemden düşülecek ücretsiz/rapor
   günleri. Varsa kıdem başlangıcı (`PSENDATE`) bu kadar gün ileri alınır.
3. `SENYEAR = GETYEARDIFF(PSENDATE, PLVDATE) + EXTRAYEAR`.
4. **Gün devri yoksa** (`DAYTRANSFER = 0`): `PSENDATE = PSENDATE + SENYEAR yıl`
   (dönem başına çekilir).
5. **`LVDAYS = GETLEAVEDAYS(...)`** — `IASHCMLEAVES`'ten ilgili dönemde
   kullanılan toplam `TOTLEAVEDAY`.
6. **`TOTEARNED = GETEARNEDLVDAYS(...)`** — `IASHCM213.LVGRPTYPE`'a göre:
   - **0 (sabit izin):** `GETCONSTYEARLV → IASHCM213.LVDAYS` (örn. 3 gün).
   - **1 (yıl bazlı / yıllık izin):** kıdem başlangıcından bugüne her tam yıl
     için, o kıdem yılına karşılık gelen dilimi (`IASHCM213D`) toplar
     (kümülatif). 18 yaş altı / 50 yaş üstü için yasal asgari 20 gün.

### 2.3 `CALCEXCLUDEDSEN` (kıdem dışı günler)
- `EXCSENLV` parametresi (`IASHCM302V`) tanımlı değilse `0`.
- `IASHCM306.EXCLUDEDSEN = 1` olan izinlerin tüm `TOTLEAVEDAY` toplamı kıdem
  dışıdır.
- `EXCLUDEDSEN = 2` (rapor/iş göremezlik) izinlerde sadece yasal sınırın
  (`GETIHBDAY(IASHCM321) + 42`) **üstündeki** günler kıdem dışı sayılır.

### Kullanılan tablolar
`IASHCMLVGRP`, `IASHCM306`/`IASHCM306X`, `IASHCM213`/`IASHCM213X`/`IASHCM213D`,
`IASHCMLEAVES`, `IASHCMPER`, `IASADRBOOKCONTACT`, `IASADRBKCNTORG`,
`IASHCM302V`, `IASHCM321`.

---

## 3. Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # CANIAS_DB_PASSWORD degerini doldurun
```

**Veritabanı bağlantısı** (ADO.NET karşılığı):

```
Data Source=DEBAKNETSIS\DB20;Initial Catalog=DBKBGYS;User ID=sa;Password=***
```

`.env` dosyasında karşılığı:

```
CANIAS_DB_SERVER=DEBAKNETSIS\DB20
CANIAS_DB_NAME=DBKBGYS
CANIAS_DB_USER=sa
CANIAS_DB_PASSWORD=<sifreniz>
```

**GR01 (Yıllık İzin) kıdem dilimleri** (kurum onaylı, `IASHCM213D`):

| Kıdem yılı | İzin günü |
|------------|-----------|
| 1–5        | 14        |
| 6–14       | 20        |
| 15+        | 26        |

Bu dilimler çalışma anında veritabanından okunur; `app/constants.py` içinde test referansı olarak tutulur.

> **ODBC sürücüsü:** MSSQL bağlantısı için sistemde *Microsoft ODBC Driver
> for SQL Server* kurulu olmalıdır (`.env` içindeki `CANIAS_DB_DRIVER`).

`.env` içindeki CANIAS sabitleri trace'in `LOGIN INFORMATION` bölümünden gelir:
`CLIENT=00`, `LANGU=T`, `COMPANY=01`, `PLANT=01`.

Bağlantı ve GR01 doğrulama:

```bash
python scripts/smoke_test.py 1028
```

---

## 4. Çalıştırma

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

İstek:

```bash
curl http://localhost:8000/personnel/1028/remaining-leaves
```

Örnek yanıt:

```json
{
  "persid": "1028",
  "company": "01",
  "as_of": "2026-06-26",
  "items": [
    {"index": 1, "field": "REM1", "leavecode": "0003", "leavegrp": "GR08",
     "name": "Diğer Ücretsiz İzin", "remaining_days": 3.0, "earned_days": 3.0,
     "used_in_period": 0.0, "carried_used": 0.0, "seniority_years": 1},
    {"index": 2, "field": "REM2", "leavecode": "0005", "leavegrp": "GR01",
     "name": "Yıllık İzin", "remaining_days": 20.0, "earned_days": 190.0,
     "used_in_period": 75.0, "carried_used": 95.0, "seniority_years": 11}
  ]
}
```

`?as_of=YYYY-MM-DD` ile geçmiş/ileri bir tarihe göre de hesaplatılabilir
(CANIAS'taki `PLVDATE`).

---

## 5. Testler

```bash
python -m pytest -q
```

Testler veritabanı gerektirmez; trace senaryosunu (PERSID 1028) bellek içi
sahte sağlayıcı ile besler ve sonucun `REM1..REM4 = 3 / 20 / 3 / 3` olduğunu
doğrular.

---

## 6. Proje Yapısı

```
app/
  config.py          # .env ayarları
  db.py              # pyodbc bağlantısı
  models.py          # alan modelleri (CANIAS tablolarıyla birebir)
  providers.py       # SQL veri erişim katmanı (trace'teki sorgular)
  canias_leave.py    # SETREMLVDAYS hesaplama motoru
  schemas.py         # API şemaları (Pydantic)
  main.py            # FastAPI uygulaması
tests/               # trace tabanlı birim testler
```

---

## 7. Önemli Notlar / Varsayımlar

- **`REMLVDAYS` türetilmiş bir değerdir.** Bu servis CANIAS mantığını yeniden
  üretir; kurum özelinde farklı `IASHCM213` ayarları (gün devri, tarih bazlı
  dilimler, aylık tahakkuk vb.) sonucu etkileyebilir. Bu durumlar kod içinde
  ilgili fonksiyonlarda işaretlenmiştir.
- Sonuçlar her zaman CANIAS HCMT101 ekranıyla **karşılaştırılarak**
  doğrulanmalıdır. Sapma olursa ilgili izin grubunun `IASHCM213`/`IASHCM213D`
  ayarları kontrol edilmelidir.
- Trace yalnızca tek bir personelin/konfigürasyonun yolunu gösterdiğinden,
  `GETIHBDAY` (rapor günü) ve yaş bazlı asgari gibi nadir dallar yürürlükteki
  4857 sayılı İş Kanunu'na göre uygulanmıştır.
```

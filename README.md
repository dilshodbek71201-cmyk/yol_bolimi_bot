# Attestatsiya Test Boti (Telegram)

Bu papkada quyidagilar bor:

- `questions.json` — yuklangan hujjatdan (Bayonnoma ilovasi) ajratib olingan
  **271 ta test savoli** va ularning variantlari (a, b, v, g).
- `answers.json` — **javoblar kaliti**. Hozircha faqat 5 ta savol uchun
  to'g'ri javob tasdiqlangan (37, 52, 65-emas, 72, 73 — qonun matniga
  asoslanib tekshirilgan). Qolgan 266 tasi `null` (bo'sh) — chunki ular
  ichki GOST/idoraviy me'yorlar bo'lib, ochiq manbada tekshirib
  bo'lmaydi. **Bularni to'ldirish uchun rasmiy javob kalitidan yoki
  instruktordan foydalaning.**

## O'rnatish

```bash
pip install -r requirements.txt
```

## Botni yaratish

1. Telegram'da **@BotFather** ga yozing.
2. `/newbot` buyrug'ini yuboring, bot nomini va username'ini kiriting.
3. BotFather sizga **token** beradi (masalan: `123456:ABC-DEF...`).

## Ishga tushirish

```bash
export BOT_TOKEN="BotFather_bergan_token"
python bot.py
```

Yoki `bot.py` faylida `TOKEN = "SIZNING_TOKENINGIZ_BU_YERGA"` qatoriga
tokenni to'g'ridan-to'g'ri yozing.

## Javoblar kalitini to'ldirish

`answers.json` faylini oching, har bir savol raqami qarshisiga to'g'ri
variant harfini yozing: `"a"`, `"b"`, `"v"` yoki `"g"`. Masalan:

```json
"5": "a",
"6": "g",
```

Faylni saqlagach, botni qayta ishga tushiring (`Ctrl+C`, keyin `python
bot.py`) — o'zgarishlar avtomatik qo'llanadi.

## Botning ishlashi

- `/start` — testni tasodifiy tartibda boshlaydi.
- Har bir savol uchun tugmalar chiqadi (А, Б, В, Г).
- Agar javob kalitida to'g'ri javob bo'lsa — ✅/❌ ko'rsatiladi.
- Agar hali kalitda yo'q bo'lsa — "tasdiqlangan javob yo'q" deb
  ko'rsatiladi, lekin savol o'tkazib yuborilmaydi.
- `/stats` — nechta savolga javob kaliti tasdiqlanganini ko'rsatadi.

## Eslatma

Bu — rasmiy attestatsiya testi. Bot faqat **o'zini-o'zi tekshirish/
tayyorgarlik** vositasi sifatida mo'ljallangan. Javoblarning
to'g'riligiga to'liq ishonch hosil qilish uchun rasmiy javob kaliti
yoki mas'ul instruktor bilan tekshiring.

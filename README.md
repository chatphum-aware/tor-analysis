# TOR Analyzer

<!-- TODO: demo GIF here — upload -> result table -> click a row -> PDF jumps to and
     highlights the cited page. Record from a real run before release; do not fabricate
     a placeholder image. -->

เครื่องมือช่วยอ่านเอกสาร TOR / ประกาศประกวดราคาของหน่วยงานราชการไทย โดยใช้ Claude API
ดึงข้อมูลสำคัญออกมาเป็นตาราง พร้อมระบุที่มา (เลขหน้า + ข้อความต้นฉบับ) และระดับความมั่นใจ
ของทุกฟิลด์ เพื่อให้ตรวจสอบย้อนกลับกับต้นฉบับได้เสมอ — ไม่ใช่แค่คำตอบที่เชื่อได้อย่างเดียว
**เครื่องมือนี้ช่วยอ่านเอกสาร ไม่ได้ตัดสินใจแทนว่าควรเข้าประมูลหรือไม่**

> ⚠️ **ยังเป็น v0.1** — ใช้ทดสอบ/ประเมินผล ยังไม่ผ่านการรีวิวเพื่อใช้งานจริงในองค์กร
> ดูหัวข้อ "ข้อจำกัดที่ควรรู้" ก่อนนำไปใช้งาน

## หลักการออกแบบ 5 ข้อ

โค้ดทั้งหมด (`schema.py`, `client.py`, prompt ที่ส่งให้โมเดล) ยึดตามกฎ 5 ข้อนี้ และ
"คุณสมบัติหลัก"/"ข้อจำกัด" ด้านล่างล้วนมาจากกฎเหล่านี้:

1. **โมเดลไม่คำนวณอะไรเลย** ไม่มีเปอร์เซ็นต์ ไม่มีแปลง พ.ศ.→ค.ศ. ไม่มีการรวมยอด/ประมาณ
   ทุกการคำนวณอยู่ในโค้ด Python เท่านั้น
2. **ทุกค่าที่ไม่ใช่ null ต้องมีที่มา** — เลขหน้า/ตำแหน่งที่แน่นอน + ข้อความต้นฉบับที่คัดมาตรง ๆ
3. **ค่าที่เป็น null ต้องมีเหตุผลกำกับ** ไม่ใช่การเดาเพื่อเติมช่องว่าง
4. **ทุกฟิลด์มีระดับความมั่นใจ** (`high`/`medium`/`low`) รวมถึงฟิลด์ที่เป็น null ด้วย
5. **ตรวจสอบ schema แล้วลองใหม่ได้ 1 ครั้ง จากนั้นถ้ายังผิดให้ล้มเหลวชัดเจน** ไม่คืนผลลัพธ์
   บางส่วนหรือผลลัพธ์ที่ถูกตัดทอนแบบเงียบ ๆ

## คุณสมบัติหลัก

- อัปโหลด PDF หรือ Word (.docx) → ได้ตารางข้อมูลที่จัดกลุ่มแล้ว (ข้อมูลพื้นฐาน, วันสำคัญ, หลักประกัน,
  คุณสมบัติผู้เสนอราคา, งวดงาน, ค่าปรับ, เอกสารที่ต้องยื่น, เกณฑ์การประเมิน, ผู้ติดต่อ)
- ทุกฟิลด์ที่มีค่า **ต้องมีที่มา** (เลขหน้า + ข้อความต้นฉบับที่คัดมาตรง ๆ) — คลิกแถวไหน
  PDF viewer จะกระโดดไปหน้านั้นและไฮไลต์ข้อความให้ (แบบ text-matching เพราะ schema ไม่มี
  bounding box — เป็น best-effort ไม่ใช่พิกัดแม่นยำ)
- ตรวจจับเอกสารสแกน (ไม่มีข้อความให้ดึง) และแจ้งชัดเจนว่าไม่รองรับ — เอกสารแบบผสม
  (มีทั้งหน้าที่เป็นข้อความและหน้าที่เป็นภาพ) จะบอกด้วยว่าหน้าไหนเป็นภาพล้วน
- ตรวจสอบไขว้จำนวนเงินที่เขียนคู่กันเป็นตัวเลขและตัวสะกด (เช่น "1,500,000 บาท
  (หนึ่งล้านห้าแสนบาทถ้วน)") ถ้าไม่ตรงกันจะขึ้นเป็นข้อควรระวัง
- คำนวณอะไรก็ตาม (% ของวงเงินงบประมาณ, แปลง พ.ศ.→ค.ศ.) ทำในโค้ด Python เสมอ
  **ไม่ให้โมเดลคำนวณเอง** เพื่อไม่ให้เลขผิดจากการคำนวณของโมเดลปนกับข้อมูลที่ดึงมาจริง
- แสดงจำนวน token ที่ใช้และค่าใช้จ่ายประมาณการ (USD และบาท) ทุกครั้งที่วิเคราะห์
- ส่งออกผลลัพธ์เป็น JSON หรือ CSV

## ตารางสถานะความสามารถ

สถานะการยืนยันของแต่ละรูปแบบไฟล์และ provider ณ ตอนนี้ — แยกชัดเจนระหว่าง "ยืนยันแล้วกับ
เอกสารจริง" กับ "เขียนโค้ด/ผ่าน unit test แล้ว แต่ยังไม่เคยรันจริง" เพราะสองสถานะนี้ไม่เท่ากัน:

| อินพุต | สถานะ |
|---|---|
| PDF ที่มีข้อความ (text layer) | ยืนยันแล้วกับเอกสารจริง |
| PDF สแกน → vision OCR | ยืนยันแล้ว (เฉพาะ Anthropic, ≤20 หน้า) |
| DOCX เนื้อหาในย่อหน้า | ยืนยันแล้วกับเอกสารจริง |
| DOCX เนื้อหาในช่องตาราง | เขียนโค้ดแล้ว ยังไม่เคยยืนยัน (ไม่มีเอกสารทดสอบที่มีค่าจากตาราง) |
| XLSX | เขียนโค้ดแล้ว ปิดไว้เป็นค่าเริ่มต้น (`TOR_ENABLE_XLSX`) ยังไม่เคยยืนยัน |
| Provider: Anthropic | ยืนยันแล้ว |
| Provider: Gemini | ยืนยันแล้วกับ 2 ใน 3 เอกสารที่ใช้ประเมินผล |
| Provider: OpenAI | เขียนโค้ดแล้ว ยังไม่เคยรันจริง (บัญชีทดสอบไม่มีเครดิต) |
| Provider: openai-compat | เขียนโค้ดแล้ว ปิด vision ไว้เป็นค่าเริ่มต้น (ตรวจสอบอัตโนมัติไม่ได้แน่นอน) |

## ข้อจำกัดที่ควรรู้ (v0.1)

- **รองรับ PDF ที่เป็นภาพสแกน (vision OCR)** — หน้าที่ไม่มี text layer จะถูกแปลงเป็นภาพ
  แล้วส่งให้โมเดลที่รองรับ vision อ่านโดยตรง แทนที่จะปฏิเสธทันที (ยืนยันแล้วว่าใช้ได้จริงกับ
  Anthropic บนเอกสารสแกนจริง 16 หน้า) — ต้องใช้ provider ที่รองรับ vision (Anthropic/OpenAI/
  Gemini รองรับเสมอ; `openai_compat` ต้องเปิดเองด้วย `TOR_OPENAI_COMPAT_VISION=1` เพราะ
  ตรวจสอบอัตโนมัติไม่ได้ว่า endpoint นั้นอ่านภาพจริงหรือเพิกเฉย) **รองรับสูงสุด 20 หน้าสแกนต่อ
  เอกสาร (`TOR_MAX_VISION_PAGES`)** — เอกสารที่เกินจะถูกปฏิเสธอย่างชัดเจน (422) ไม่ใช่ตัดหน้าทิ้ง
  เงียบ ๆ **นี่คือข้อจำกัดที่ใหญ่ที่สุดของ v0.1**: TOR ของจริงมักยาว 80–200 หน้า ดังนั้นเอกสารสแกน
  ขนาดใหญ่ส่วนมากจะยังใช้ไม่ได้ในตอนนี้
- **การวิเคราะห์เอกสารสแกนผ่าน vision ใช้เวลานาน และอาจชน timeout** — เอกสารสแกน 16 หน้า
  วัดจริงแล้วใช้เวลาประมาณ 250 วินาทีต่อการวิเคราะห์ 1 ครั้ง (ส่ง 6 ครั้งเรียงกันไปยัง API
  แต่ละครั้งพ่วงภาพทั้ง 16 หน้า) ใกล้เพดาน `EXTRACTION_TIMEOUT_SECONDS` ค่าเริ่มต้น 300 วินาที
  มาก และหากคำขอแรกชน timeout แล้วลองใหม่ทันที คำขอเดิมยังทำงานต่อในเบื้องหลัง
  (เพราะยกเลิก thread ไม่ได้จริง) แย่งอัตราเรียก API เดียวกัน ทำให้คำขอที่ลองใหม่มีโอกาสชน
  timeout ซ้ำอีก — ยังไม่ได้แก้ใน v0.1
- **รองรับไฟล์ Word (.docx)** นอกเหนือจาก PDF แล้ว — อ้างอิงตำแหน่งด้วยย่อหน้า/ช่องตาราง
  แทนเลขหน้า (ไฟล์ Word ไม่มีเลขหน้าจริงในไฟล์) ยืนยันแล้วกับ TOR จริงของหน่วยงานท้องถิ่น
- **ไฮไลต์ใน PDF เป็น best-effort** ใช้การจับคู่ข้อความกับ text layer ของ pdf.js ไม่ใช่พิกัด
  bounding box จริง เอกสารที่ข้อความถูกตัดคำแปลก ๆ อาจไฮไลต์ไม่ครบ
- **การแคช prompt ข้ามกลุ่มฟิลด์ใช้ไม่ได้จริง** — การดึงข้อมูลแบ่งเป็น 6 กลุ่ม
  (`backend/app/llm/groups.py`) เพราะ schema เดียวรวมทุกฟิลด์ทำให้ API ปฏิเสธ
  ("compiled grammar is too large") แต่ผลคือแต่ละกลุ่มมี schema ต่างกัน ทำให้ cache prefix
  ขาดทุกครั้ง แคชช่วยได้แค่ตอน retry ในกลุ่มเดียวกัน หรือรันเอกสาร+กลุ่มเดิมซ้ำภายใน TTL
- **โมเดลราคาถูก (เช่น Haiku) มีโอกาสอนุมาน/คำนวณค่าที่เอกสารไม่ได้เขียนไว้ตรง ๆ**
  ในบางฟิลด์ (พบจากการทำ eval จริง แก้ทีละจุดที่เจอแล้ว แต่ไม่รับประกันว่าจะไม่เจอฟิลด์ใหม่
  เมื่อทดสอบเอกสารหลากหลายขึ้น) — ดูผลการทดสอบใน [หัวข้อ "การประเมินผล"](#การประเมินผล)
- **รองรับหลาย LLM provider แล้ว** (Anthropic, OpenAI, Gemini, และ OpenAI-compatible
  endpoint ใด ๆ เช่น Ollama/vLLM/Groq/OpenRouter สำหรับ Llama/Qwen ฯลฯ — ดูตัวแปร
  `TOR_PROVIDER` ใน `.env.example`) แต่ **ผ่านการทดสอบจริงในระดับต่างกัน**: Anthropic
  ผ่านครบทุกเอกสารทดสอบไม่มี crash เลย ส่วน provider อื่นมี adapter ที่ผ่าน unit test
  ครบแล้วแต่ eval แบบเต็มยังติดปัญหาเรื่อง account/quota ของผู้ทดสอบเอง (ไม่ใช่บั๊กโค้ด) —
  โมเดล reasoning บางตัวผ่าน OpenAI-compatible endpoint ยังมีข้อจำกัดจริงที่พบระหว่างทดสอบ
  ด้วย (token budget, rate limit) ดู [หัวข้อ "การประเมินผล"](#การประเมินผล)

## การติดตั้งและรัน

ต้องมี: [Docker](https://docs.docker.com/get-docker/), [Node.js](https://nodejs.org/) 18+,
และ Anthropic API key ของคุณเอง (bring-your-own-key)

```bash
# 1. ตั้งค่า environment
cp .env.example .env
# แก้ .env ใส่ ANTHROPIC_API_KEY ของคุณเอง

# 2. รัน backend (FastAPI, พอร์ต 8000)
docker compose up -d

# 3. รัน frontend แยกต่างหาก (ยังไม่มี Docker service ให้ frontend)
cd frontend
npm install
npm run dev   # เปิดที่ http://localhost:5173
```

เปิด `http://localhost:5173` แล้วอัปโหลด PDF หรือ .docx ได้เลย

## Environment variables

ดูรายละเอียดทั้งหมดใน `.env.example` ตัวแปรหลัก ๆ:

| ตัวแปร | ความหมาย |
|---|---|
| `TOR_PROVIDER` | provider ที่จะใช้: `anthropic` (default) \| `openai` \| `gemini` \| `openai_compat` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `TOR_PROVIDER_API_KEY` | API key ของคุณเอง — ชื่อตัวแปรขึ้นกับ `TOR_PROVIDER` ที่เลือก (จำเป็น) |
| `TOR_PROVIDER_BASE_URL` | ใช้เฉพาะ `TOR_PROVIDER=openai_compat` — base URL ของ endpoint (Ollama/vLLM/Groq/OpenRouter ฯลฯ) |
| `TOR_MODEL` | โมเดลที่ใช้สกัดข้อมูล (แนะนำ `claude-opus-5` สำหรับผลลัพธ์จริง, `claude-haiku-4-5`/`claude-sonnet-5` สำหรับพัฒนา/ทดสอบ) |
| `TOR_GROUP_<GROUP>` | (optional) สั่งให้ field group หนึ่งใช้ provider/model ต่างจากค่า default เช่น `TOR_GROUP_QUALIFICATIONS=anthropic:claude-opus-5` |
| `USD_THB_RATE`, `USD_THB_RATE_DATE` | อัตราแลกเปลี่ยนสำหรับแสดงค่าใช้จ่ายเป็นบาท (ต้องอัปเดตเองเป็นระยะ) |
| `MAX_UPLOAD_MB` | ขนาดไฟล์อัปโหลดสูงสุด |
| `CORS_ORIGINS` | origin ของ frontend ที่อนุญาต |
| `EXTRACTION_TIMEOUT_SECONDS` | เวลาสูงสุดที่ยอมให้การวิเคราะห์หนึ่งครั้งใช้ (default 300 วินาที — ดูข้อจำกัดเรื่อง vision ด้านบน) |
| `TOR_ENABLE_XLSX` | เปิดรองรับไฟล์ .xlsx (ปิดเป็นค่าเริ่มต้น ยังไม่เคยยืนยันกับ TOR จริง) |
| `TOR_OPENAI_COMPAT_VISION` | เปิดส่งภาพให้ endpoint แบบ `openai_compat` (ปิดเป็นค่าเริ่มต้น) |
| `TOR_MAX_VISION_PAGES` | จำนวนหน้าสแกนสูงสุดต่อเอกสารที่ส่งให้ vision model (default 20) |
| `TOR_MAX_VISION_PAYLOAD_BYTES` | ขนาดรวมสูงสุดของภาพที่ส่งให้ vision model (default 20MB) |

## API

| Endpoint | คำอธิบาย |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/extract` | อัปโหลดไฟล์ (multipart) → คืนผลลัพธ์ `TORDocument` — รูปแบบไฟล์ตรวจจากเนื้อไฟล์จริง ไม่ใช่นามสกุล: PDF, DOCX เสมอ, XLSX ถ้าเปิด `TOR_ENABLE_XLSX` |
| `POST /api/export/csv` | รับ `TORDocument` → คืนไฟล์ CSV |

## CLI (สำหรับ debug/พัฒนา)

```bash
cd backend
python -m app.pdf.extract path/to/document.pdf      # ตรวจสอบว่าไฟล์ดึงข้อความได้ไหม
ANTHROPIC_API_KEY=... python -m app.run_extraction path/to/document.pdf  # รันเต็ม pipeline
```

## การประเมินผล

`backend/app/eval/` มีชุดทดสอบกับเอกสารจริง 3 ฉบับจากเว็บไซต์หน่วยงานราชการ
(ที่มา + เหตุผลการคัดเลือกอยู่ใน `backend/tests/fixtures/samples.json`):

```bash
cd backend
python -m app.eval.fetch_samples          # ดาวน์โหลด PDF ตัวอย่าง (ไม่ commit ไฟล์ PDF)
ANTHROPIC_API_KEY=... python -m app.eval.run_eval --model claude-opus-5
```

ให้ผลเป็นตาราง markdown นับรายฟิลด์เป็น exact / wrong / missed / hallucinated
(รายงานเป็นจำนวนนับ ไม่ใช่ % เพราะ n=3 เอกสารน้อยเกินกว่าจะอ้างเปอร์เซ็นต์ได้อย่างซื่อสัตย์)
ผลล่าสุด (claude-opus-5, หลังแก้บั๊กที่เจอระหว่างทำ eval): 185/215 ฟิลด์ตรงเป๊ะ, 0 missed —
ดูรายละเอียดและบั๊กที่เจอ+แก้แล้วทั้งหมดใน `PROGRESS.md`

**เปรียบเทียบข้าม provider**: `python -m app.eval.compare_providers --eval --provider <p1>
--model <m1> --provider <p2> --model <m2> ...` (มีโหมด `--check-schema-ceiling` สำหรับเช็ค
เร็ว ๆ ว่า provider ตอบ schema แต่ละกลุ่มได้ไหม ก่อนรัน eval เต็ม) ผลล่าสุด: `anthropic`
(claude-haiku-4-5) ผ่านครบ 3 เอกสาร 195/215 ตรงเป๊ะ (91%) ไม่มี crash เลย ค่าใช้จ่าย $0.6177
ส่วน self-hosted/OpenAI-compatible model บางตัว (ทดสอบกับ `openai/gpt-oss-120b` ผ่าน Groq)
มีข้อจำกัดจริงที่พบระหว่างทดสอบ — token budget ไม่พอสำหรับ reasoning model, ไม่ยอมใส่ reason
ตอนค่าเป็น null (ผ่าน JSON schema แต่ไม่ผ่านกฎภายในของโปรเจกต์), และ rate limit ของ free tier
ต่ำเกินไปสำหรับเอกสารจริงที่ยาว — ดู `PROGRESS.md` และ `docs/plans/2026-09-02-multi-provider-
migration.md` สำหรับรายละเอียดทั้งหมด

## ค่าใช้จ่ายจริงที่วัดได้

ค่าใช้จ่ายต่อเอกสาร (ไม่ใช่ผลรวมทั้งชุด eval) จากการรันจริงที่บันทึกไว้ใน `PROGRESS.md`:

- **เอกสาร PDF แบบ hybrid 77 หน้า มีข้อความจริงแค่ ~16% ของหน้า** (ก่อนมี vision OCR หน้าที่
  เหลือเป็นภาพล้วนจึงไม่ถูกอ่านเลยในการวัดนี้): **$0.138** (~฿5.05, Haiku) — ยังไม่มีตัวเลขจาก
  PDF ที่มีข้อความปกติล้วนทั้งฉบับที่วัดแยกไว้ต่างหาก
- **เอกสารสแกนล้วน 16 หน้า ผ่าน vision OCR ทั้งฉบับ**: **$0.2630** (Haiku)
- ค่าใช้จ่ายขึ้นกับราคาของ provider/model ที่เลือกและความยาวเอกสารจริง ตัวเลขข้างบนใช้
  `claude-haiku-4-5` ไม่ใช่ `claude-opus-5` ที่แนะนำสำหรับผลลัพธ์จริง

## License

**GNU Affero General Public License v3.0 (AGPL-3.0)** — ดู [`LICENSE`](./LICENSE)

โปรเจกต์นี้ใช้ [PyMuPDF](https://pypi.org/project/PyMuPDF/) ซึ่ง dual-license เป็น
AGPL-3.0 หรือ Artifex Commercial License เนื่องจากไม่ได้ซื้อ commercial license
ทั้งโปรเจกต์จึงอยู่ภายใต้ AGPL-3.0 **ข้อควรรู้**: AGPL กำหนดว่าถ้านำซอฟต์แวร์นี้
(หรือเวอร์ชันที่แก้ไข) ไปให้บริการผ่านเครือข่าย (network service) ต้องเปิดเผย source code
ของเวอร์ชันที่รันอยู่ให้ผู้ใช้บริการเข้าถึงได้ด้วย (มาตรา 13) — ไม่ใช่แค่ MIT/BSD ทั่วไป
ถ้าจะนำไปใช้แบบปิด source เชิงพาณิชย์ ต้องมี Artifex commercial license หรือเปลี่ยนไปใช้
ไลบรารีอื่นแทน PyMuPDF (โค้ดที่พึ่งพา PyMuPDF โดยตรงคือ `backend/app/pdf/extract.py` และ
`backend/app/pdf/scanned.py`)
(หมายเหตุ: นี่ไม่ใช่คำแนะนำทางกฎหมาย ควรตรวจสอบกับที่ปรึกษากฎหมายก่อนนำไปใช้เชิงพาณิชย์)

---

# TOR Analyzer

A tool for reading Thai government TOR / procurement announcement documents using the
Claude API, extracting key fields into a review table with a citation (page number +
original quote) and a confidence level on every field — so every answer stays checkable
against the source, not just something to take on faith. **This is a tool that helps
people read documents; it does not decide whether to bid.**

> ⚠️ **Still v0.1** — built for testing and evaluation, not yet reviewed for production
> use in an organization. Read "Known limitations" before relying on it.

## Design rules

Everything in this codebase (`schema.py`, `client.py`, the prompts sent to the model)
follows these five rules, and the Features/Limitations sections below are consequences of
them, not separate design choices:

1. **The model never computes anything.** No percentages, no Buddhist-Era→Common-Era
   date conversion, no summing or estimating. All arithmetic happens in Python code.
2. **Every non-null value carries a source** — an exact page/locator plus a verbatim
   quote from the document.
3. **A null value carries a reason**, never a guess used to fill the slot.
4. **Every field carries a confidence level** (`high`/`medium`/`low`), including null ones.
5. **Schema validation gets one retry, then a loud failure** — never a partial or
   silently-truncated result.

## Features

- Upload a PDF or Word (.docx) → get a grouped result table (basic info, key dates, bonds,
  bidder qualifications, deliverables/payment schedule, penalties, required documents,
  evaluation criteria, contact)
- Every non-null field **must carry a source** (page number + a verbatim quote) —
  clicking a row jumps the PDF viewer to that page and highlights the matching text
  (text-matching against pdf.js's text layer, since the schema has no bounding box —
  best-effort, not pixel-exact)
- Detects fully-scanned documents (no extractable text) and says so clearly rather than
  returning an empty table; detects mixed documents and flags which pages are image-only
- Cross-checks amounts written both as digits and spelled-out words (e.g.
  "1,500,000 บาท (หนึ่งล้านห้าแสนบาทถ้วน)") and flags a mismatch if they disagree
- All arithmetic (bond % of budget, Buddhist-Era → Common-Era date conversion) happens in
  Python code, **never delegated to the model** — so a model computation error can never
  masquerade as an extracted fact
- Shows token usage and an estimated cost (USD and Thai baht) for every analysis run
- Export results as JSON or CSV

## Capability matrix

The verification status of every input format and provider, as of now — kept distinct on
purpose, because "verified against a real document" and "built and unit-tested but never
run live" are not the same claim:

| Input | Status |
|---|---|
| PDF, embedded text | Verified against real documents |
| PDF, scanned → vision OCR | Verified (Anthropic only, ≤20 pages) |
| DOCX, paragraph content | Verified against a real document |
| DOCX, table-cell content | Implemented, never verified (no test document had table values) |
| XLSX | Implemented, disabled by default (`TOR_ENABLE_XLSX`), never verified |
| Provider: Anthropic | Verified |
| Provider: Gemini | Verified on 2 of 3 eval documents |
| Provider: OpenAI | Implemented, never run (account had no credit) |
| Provider: openai-compat | Implemented, vision off by default (auto-probe unreliable) |

## Known limitations (v0.1)

- **Scanned PDFs are supported via vision OCR** — a page with no text layer is rendered
  as an image and sent directly to a vision-capable model, rather than being rejected
  outright (verified live against a real 16-page scanned document on Anthropic). Requires
  a vision-capable provider (Anthropic/OpenAI/Gemini always qualify; `openai_compat`
  needs an explicit `TOR_OPENAI_COMPAT_VISION=1` opt-in, since there's no reliable way to
  auto-detect whether an endpoint actually reads the image or silently ignores it).
  **Capped at 20 scanned pages per document (`TOR_MAX_VISION_PAGES`)** — anything larger
  is rejected clearly (422) rather than having pages silently dropped. **This is the
  single largest gap in v0.1**: real Thai TORs routinely run 80–200 pages, so most large
  scanned documents don't work here yet.
- **A scanned-document vision run is slow, and can hit the timeout** — a real 16-page
  scanned document measured at ~250 seconds for one clean analysis (6 sequential API
  calls, each carrying all 16 page images), uncomfortably close to the default 300s
  `EXTRACTION_TIMEOUT_SECONDS` ceiling. Worse, if a request times out and you retry
  immediately, the original request keeps running server-side (the thread can't actually
  be cancelled) and competes for the same rate limit, making the retry more likely to
  time out too. Not fixed in v0.1.
- **Word (.docx) is supported** alongside PDF — citations use a paragraph/table-cell
  locator instead of a page number (Word files have no real page count), verified against
  a real local-government TOR document.
- **PDF highlighting is best-effort**, matched against pdf.js's text layer rather than
  true bounding-box coordinates — unusually segmented text may highlight incompletely
- **Cross-group prompt caching doesn't actually work** — extraction is split into 6
  field groups (`backend/app/llm/groups.py`) because sending the whole schema in one call
  gets rejected by the API ("compiled grammar is too large"), but each group has a
  different schema, which breaks the cache prefix every time. Caching only helps a
  same-group retry, or re-running the same document+group again within the TTL.
- **Cheaper models (e.g. Haiku) have shown a tendency to infer/compute values the
  document never actually states**, in specific fields (found via real eval runs, fixed
  as found, but not guaranteed to be fully closed off against new documents) — see
  [Evaluation](#evaluation) for the latest numbers.
- **Multiple LLM providers are supported** (Anthropic, OpenAI, Gemini, and any
  OpenAI-compatible endpoint — Ollama/vLLM/Groq/OpenRouter, etc., for Llama/Qwen and other
  self-hosted models — see `TOR_PROVIDER` in `.env.example`), but **verified to different
  degrees**: Anthropic has completed every test document with zero crashes; the other
  adapters pass their unit tests but a full eval run hit real account/quota limits on the
  tester's own accounts (not code bugs) — and one reasoning model tested via an
  OpenAI-compatible endpoint surfaced genuine limitations of its own (token budget, rate
  limits) — see [Evaluation](#evaluation).

## Setup

Requires: [Docker](https://docs.docker.com/get-docker/), [Node.js](https://nodejs.org/) 18+,
and your own Anthropic API key (bring-your-own-key).

```bash
# 1. Configure environment
cp .env.example .env
# edit .env and fill in your own ANTHROPIC_API_KEY

# 2. Run the backend (FastAPI, port 8000)
docker compose up -d

# 3. Run the frontend separately (no Docker service for it yet)
cd frontend
npm install
npm run dev   # opens at http://localhost:5173
```

Open `http://localhost:5173` and upload a PDF or .docx file.

## Environment variables

See `.env.example` for the full list. Key ones:

| Variable | Meaning |
|---|---|
| `TOR_PROVIDER` | Which provider to use: `anthropic` (default) \| `openai` \| `gemini` \| `openai_compat` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `TOR_PROVIDER_API_KEY` | Your own API key — the variable name depends on `TOR_PROVIDER` (required) |
| `TOR_PROVIDER_BASE_URL` | Only for `TOR_PROVIDER=openai_compat` — the endpoint's base URL (Ollama/vLLM/Groq/OpenRouter, etc.) |
| `TOR_MODEL` | Extraction model (`claude-opus-5` recommended for real results, `claude-haiku-4-5`/`claude-sonnet-5` for dev/testing) |
| `TOR_GROUP_<GROUP>` | (optional) run one field group on a different provider/model than the default, e.g. `TOR_GROUP_QUALIFICATIONS=anthropic:claude-opus-5` |
| `USD_THB_RATE`, `USD_THB_RATE_DATE` | Exchange rate for displaying cost in baht (update periodically) |
| `MAX_UPLOAD_MB` | Max upload file size |
| `CORS_ORIGINS` | Allowed frontend origin(s) |
| `EXTRACTION_TIMEOUT_SECONDS` | Max time allowed for one analysis run (default 300s — see the vision limitation above) |
| `TOR_ENABLE_XLSX` | Enable .xlsx uploads (off by default, never verified against a real TOR) |
| `TOR_OPENAI_COMPAT_VISION` | Enable sending images to an `openai_compat` endpoint (off by default) |
| `TOR_MAX_VISION_PAGES` | Max scanned pages per document sent to the vision model (default 20) |
| `TOR_MAX_VISION_PAYLOAD_BYTES` | Max combined size of images sent to the vision model (default 20MB) |

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | health check |
| `POST /api/extract` | upload a file (multipart) → returns a `TORDocument` — format is sniffed from file content, not the extension: PDF and DOCX always, XLSX if `TOR_ENABLE_XLSX` is set |
| `POST /api/export/csv` | takes a `TORDocument` → returns a CSV file |

## CLI (dev/debugging)

```bash
cd backend
python -m app.pdf.extract path/to/document.pdf      # check whether text extraction works
ANTHROPIC_API_KEY=... python -m app.run_extraction path/to/document.pdf  # run the full pipeline
```

## Evaluation

`backend/app/eval/` holds an eval harness tested against 3 real documents fetched from
government websites (sourcing rationale in `backend/tests/fixtures/samples.json`):

```bash
cd backend
python -m app.eval.fetch_samples          # download the pinned sample PDFs (not committed)
ANTHROPIC_API_KEY=... python -m app.eval.run_eval --model claude-opus-5
```

Produces a markdown table scoring each field as exact / wrong / missed / hallucinated
(reported as raw counts, not percentages — n=3 documents is too small to honestly claim a
%). Latest result (claude-opus-5, after fixing the bugs found during eval): 185/215 fields
exact, 0 missed — see `PROGRESS.md` for the full list of bugs found and fixed along the way.

**Cross-provider comparison**: `python -m app.eval.compare_providers --eval --provider <p1>
--model <m1> --provider <p2> --model <m2> ...` (also has a `--check-schema-ceiling` mode for
a quick sanity check of whether a provider can answer each group's schema before running the
full eval). Latest result: `anthropic` (claude-haiku-4-5) completed all 3 documents cleanly
at 195/215 exact (91%), zero crashes, $0.6177. A self-hosted/OpenAI-compatible model tested
via Groq (`openai/gpt-oss-120b`) surfaced real limitations worth knowing about before relying
on this path: insufficient token budget for a reasoning model, a tendency to satisfy the JSON
schema's `required` constraint without satisfying this project's own null-needs-a-reason rule,
and a free-tier rate limit too low for our longer real documents — see `PROGRESS.md` and
`docs/plans/2026-09-02-multi-provider-migration.md` for full detail.

## Measured cost

Per-document cost (not the 3-document eval total) from real recorded runs in `PROGRESS.md`:

- **A 77-page hybrid PDF with only ~16% real text** (pre-vision-OCR; the remaining
  image-only pages simply weren't read in this measurement): **$0.138** (Haiku) — there
  isn't yet a separately measured figure for a normal, fully text-based PDF.
- **A fully scanned 16-page document, entirely via vision OCR**: **$0.2630** (Haiku)
- Cost depends on the provider/model you choose and the document's real length. The
  figures above are `claude-haiku-4-5`, not the `claude-opus-5` recommended for real use.

## License

**GNU Affero General Public License v3.0 (AGPL-3.0)** — see [`LICENSE`](./LICENSE).

This project depends on [PyMuPDF](https://pypi.org/project/PyMuPDF/), which is dual-licensed
under AGPL-3.0 or a commercial Artifex license. Since no commercial license was purchased,
the whole project is licensed AGPL-3.0. **Note**: AGPL requires that if you run this
software (or a modified version of it) as a network service, you must make the
corresponding source code of the version you're running available to its users (Section 13)
— a stronger requirement than a typical MIT/BSD license. A closed-source commercial
deployment needs either an Artifex commercial license or a replacement for PyMuPDF (the
code that depends on it directly is `backend/app/pdf/extract.py` and
`backend/app/pdf/scanned.py`).
(This is not legal advice — consult a lawyer before any commercial use.)

# TOR Analyzer — สถานะงาน (ต่อจากตรงนี้ได้)

ไฟล์นี้มีไว้ให้ Claude (หรือใครก็ตาม) เปิดงานต่อได้ทันทีถ้าเซสชันขาดหรือเครื่องปิดกะทันหัน
อ่านไฟล์นี้ก่อน แล้วดูแผนเต็มที่ `~/.claude/plans/for-this-project-i-elegant-spring.md`
(multi-provider migration) หรือ `~/.claude/plans/valiant-booping-sloth.md` (multi-format
ingestion + vision OCR — งานล่าสุด ดูหัวข้อท้ายไฟล์นี้) — ทั้งสองไฟล์มีเหตุผล/หลักฐานเบื้องหลัง
การตัดสินใจทุกอย่างละเอียดกว่านี้มาก

**อัปเดตล่าสุด:** 2026-09-03

---

## สถานะ repo

- **มี commit จริงแล้ว** (ผ่าน `/quick-commit` เท่านั้น ไม่เคย commit ตรงเองเลย):
  `f716f69` Initial commit -> `5bb5fff` Update README.md -> `cdd4358` Add TOR Analyzer app ->
  `4992e47` Add LLM provider abstraction (Anthropic/OpenAI/Gemini) -> `502dc31` Fix 10
  code-review findings in multi-provider pipeline -> `c73c66f` Add DOCX/XLSX ingestion and
  generalized source citations (Phase 1-4 ของงาน multi-format ingestion — ดูหัวข้อท้ายไฟล์)
  Phase 5 (vision OCR สำหรับ PDF ที่สแกน) **ยังไม่ได้ commit** ตอนเขียนบรรทัดนี้
  ถ้าเซสชันขาด ให้เช็ค `git log --oneline` และ `git status` ก่อนเสมอว่า commit ไปถึงไหนแล้วจริง ๆ
- ห้าม commit เองโดยไม่ผ่าน `/quick-commit` ตาม CLAUDE.md ของผู้ใช้
- มีไฟล์ `doh_root.html` ที่ root — **ไม่ใช่ไฟล์ที่ Claude สร้าง** ดูเหมือนผู้ใช้บันทึกหน้าเว็บ
  procurement.doh.go.th ไว้เอง (อาจเกี่ยวกับการหาตัวอย่างเอกสาร) ไม่ต้องยุ่งกับมันถ้าไม่รู้ว่าคืออะไร

## ทำเสร็จแล้ว (verified จริง ไม่ใช่แค่เขียนโค้ด)

- **Step 1** — PDF → ข้อความไทย + per-page scan report (`backend/app/pdf/`, `backend/app/thai/`)
  ทดสอบกับไฟล์จริง 2 ไฟล์ที่ `~/Downloads/`: `29_44_Attach_TOR_1.pdf` (สแกนล้วน),
  `799_823_Attach_TOR_1.pdf` (hybrid, มีข้อความจริงแค่ ~16% ของ 77 หน้า)
- **Step 2** — Pydantic schema (`backend/app/models/schema.py`) + Thai number-word parser
  (`backend/app/thai/numbers.py`) — unit tested ครบ
- **Step 3** — Claude API extraction call จริง (Haiku) **ใช้ได้จริง แต่โครงสร้างเปลี่ยนกลางทาง**:
  schema เดียวรวมทุกฟิลด์ยิง API แล้วได้ 400 "compiled grammar is too large" —
  แก้โดยแตกเป็น **6 FieldGroup** (`backend/app/llm/groups.py`) และพบว่า **cross-group caching
  ใช้ไม่ได้จริง** (schema ต่างกันต่อ group ทำให้ cache prefix ขาด) — ตัดสินใจแล้วว่ายอมรับสภาพนี้ใน v0.1
- **Step 4** — FastAPI + docker compose (`backend/app/main.py`, `backend/app/api/`,
  `backend/Dockerfile`, `docker-compose.yml`) — ทดสอบผ่าน `docker compose up` จริง
  รวมถึงยิง extraction จริงผ่าน container สำเร็จ ($0.138 / ~฿5.05)
  **พบและแก้บั๊กจริงระหว่างทาง**: root `.env` มี `TOR_MODEL=claude-haiku-5` (พิมพ์ผิด
  ไม่มีโมเดลนี้จริง) แก้เป็น `claude-haiku-4-5` แล้ว
- **Step 5 — เสร็จแล้ว ทดสอบจริงจบแล้ว** — React UI (`frontend/`):
  `UploadPane`, `ResultTable`, `PdfViewer` (highlight แบบ text-match เพราะ schema ไม่มี bbox),
  `ScannedNotice`, `UsageFooter`, `ExportButtons`
  - `npx tsc -b` ผ่าน, `npm run build` ผ่าน
  - ทดสอบในเบราว์เซอร์จริงผ่าน mock backend ก่อน (ไม่เสีย API budget) แล้วเจอ 2 บั๊กจริง แก้แล้ว:
    1. **PDF highlight ทับตัวหนังสือจนอ่านไม่ออก** — `mark.pdf-highlight` ใช้ `background: #ffe066`
       ทึบแสง ซึ่งอยู่ใน text layer ของ react-pdf (z-index ทับ canvas ที่วาดตัวอักษรจริง) เลยบัง
       ตัวอักษร แก้เป็น `rgba(255,224,102,0.55)` + `mix-blend-mode: multiply` ใน
       `frontend/src/index.css` ให้เป็น highlighter โปร่งแสงแทน
    2. **คลิกแถวในตารางแล้วไม่รู้ว่า highlight ใน PDF ตรงกับแถวไหน** — เพิ่ม active-row indicator:
       thread `selectedSource` (มีอยู่แล้วใน `App.tsx`) ผ่านเข้า `ResultTable` ->  `SourcedRow`
       ทุกจุดเรียก เทียบด้วย `isSameSource` (page+quote) ใส่ class `row-active` /
       `risk-flag-active` (พื้นฟ้าอ่อน + แถบซ้ายสีฟ้า `--accent`)
  - **ทดสอบ live extraction ผ่าน UI จริงแล้ว (ไม่ใช่ mock)** — สลับจาก mock backend เป็น
    `docker compose up -d` (backend จริง, `TOR_MODEL=claude-haiku-4-5`), อัปโหลด
    `799_823_Attach_TOR_1.pdf` ผ่าน `http://localhost:5173` จริง ได้ผล 200 OK,
    active-row indicator ทำงานถูกต้องตามที่ผู้ใช้ยืนยัน, ค่าใช้จ่าย $0.1389 (~฿5.07),
    84.5 วินาที — ตรงกับตัวเลขที่เคยวัดได้ตอน Step 4 (project_name/agency/budget_amount
    ตรงกับผลอ้างอิงเป๊ะ, budget_amount/median_price/key_dates เป็น None/0 เหมือนกันทั้งคู่ —
    ไม่ใช่ regression เป็นเพราะเอกสารนี้มีข้อความใช้ได้แค่ ~16% ของหน้า)
  - หมายเหตุ: container เก่าจาก Step 4 ถูกสร้างด้วย `docker run` ตรง ๆ ไม่ใช่ `docker compose`
    ทำให้ label ไม่ครบ `docker compose up` recreate ไม่ได้ (`strconv.Atoi` error) —
    ลบ container เก่านั้นทิ้งแล้ว (แค่ stopped container ไม่มี volume ไม่เสียข้อมูลอะไร)

## สถานะ background processes ปัจจุบัน

- **Real backend** (ไม่ใช่ mock แล้ว) รันผ่าน `docker compose up -d` บน port 8000
  (`docker compose ps` เพื่อเช็ค, `docker compose logs backend` เพื่อดู log)
- Vite dev server บน port 5173 (`npm run dev` ใน `frontend/`) ยังรันค้างจากเซสชันก่อนหน้า
- mock backend script (`.../scratchpad/mock_backend.py`) เลิกใช้แล้ว ถูก kill ไปตอนสลับมาใช้ backend จริง

- **Step 6 — Eval: เสร็จแล้ว ทดสอบจริงจบแล้ว (นี่คือ step ที่แผนบอกว่าสำคัญที่สุด และพบบั๊กจริง 2 ตัว)**
  - `backend/app/eval/fetch_samples.py` + `backend/tests/fixtures/samples.json`: ดาวน์โหลด PDF
    จริงจาก 2 แหล่ง — `interapp4.rd.go.th/TPW/` (ไม่มี robots.txt) และ `audit.go.th`
    (มี robots.txt, `Crawl-delay: 10` — เคารพแล้วในสคริปต์) รวม 6 ไฟล์ pin URL ไว้
    ใช้จริงเป็น eval fixtures 3 ไฟล์ (`tor_2400`, `tor_2733`, `audit_26394_bidding`)
    อีก 3 ไฟล์คัดออกแต่เก็บไว้ใน samples.json พร้อมเหตุผล (`post_8000` สแกนล้วน,
    `post_7000` ฟอนต์ไม่มี ToUnicode CMap ข้อความเพี้ยนเป็นตัวอักษรมั่ว, `audit_26394_tor`
    ซ้ำเคสกับ `audit_26394_bidding`)
  - **พบจริง**: `usable_text_ratio=100%` ไม่พอจะบอกว่าข้อความอ่านได้จริง — `post_7000` ได้ 100%
    แต่ข้อความที่ได้เป็นตัวอักษรละตินมั่ว (ฟอนต์ชื่อ "Helvetica" ที่จริงเป็น subset ฟอนต์ไทยไม่มี
    ToUnicode CMap) ทั้ง `usable_text_ratio` และ `find_glyph_order_anomalies` ตรวจจับไม่ได้
    ต้องอ่านข้อความที่ดึงออกมาด้วยตาจริงถึงจะเจอ — ยังไม่มี automated check สำหรับเคสนี้ (to-do)
  - `backend/tests/expected/*.json`: กำกับมือ 3 ฉบับเต็ม schema (ไม่มี PII จริงในเอกสารทั้ง 3 —
    ไม่มีเบอร์/อีเมลเจ้าหน้าที่เลยในเนื้อหาจริง จึงไม่ต้อง redact) ไม่รวม `extraction_meta`
    ตามแผน (usage/cost/duration เปลี่ยนทุกรอบ ให้คะแนนไม่ได้)
  - `backend/app/eval/run_eval.py`: ให้คะแนนราย field เป็น exact/wrong/missed/hallucinated
    (ตาม `.value` เท่านั้น ไม่รวม confidence/source/reason) ยกเว้น `risk_flags` จากการให้คะแนน
    แบบ leaf (เป็น free-form text เทียบตรงกับ ground truth ไม่ได้จริง) รายงานผลเป็น markdown
    table พร้อมค่าใช้จ่ายรวม — ทดสอบ logic offline (self-compare + perturbation) ก่อนยิง API จริง
  - **บั๊กจริงที่เจอระหว่าง eval (แก้แล้วทั้งคู่)**:
    1. `group_qualifications.md` บอกให้ดึง "ทุกข้อ" ของคุณสมบัติ — เอกสารจริงมีข้อกฎหมายทั่วไป
       (ไม่ล้มละลาย, ไม่ถูกขึ้นบัญชีดำ ฯลฯ) 11-13 ข้อในแทบทุกฉบับ ทำให้ JSON ยาวเกิน
       `MAX_TOKENS=8000` ต่อกลุ่ม — แก้โดยจำกัด prompt ให้ดึงเฉพาะคุณสมบัติที่มีเกณฑ์ตรวจสอบได้จริง
       (ตัวเลข/ชื่อใบอนุญาต/มาตรฐาน) ห้ามดึงข้อกฎหมายทั่วไป — ยืนยันแล้วว่า `tor_2733` ผ่านหลังแก้
    2. `group_key_dates.md` แสดง 5 ประเภทวันสำคัญไว้ในprompt — โมเดลพยายามสร้างรายการให้ครบ
       ทั้ง 5 ประเภทแม้เอกสารไม่ได้พูดถึงประเภทนั้นเลย (เช่น `audit_26394_bidding` พูดถึงแค่
       "ยื่นข้อเสนอ" ประเภทเดียว แต่โมเดลสร้าง 5 รายการ) ทำให้ field `type` ไม่มี source
       (ยืนยัน root cause ด้วยการเทียบ error กับเนื้อหาเอกสารจริงตรง ๆ ไม่ใช่เดา) — แก้โดยเพิ่ม
       ประโยคห้ามสร้างรายการสำหรับประเภทที่เอกสารไม่ได้พูดถึงจริง ใน prompt
    3. **ปัญหาที่มาด้วยกัน (ไม่ใช่ root cause แต่ทำให้บั๊กข้างบนกลายเป็น hard fail)**:
       `llm/client.py` retry (rule #5 — ลองครั้งเดียวแล้ว error ชัดเจน) เดิมส่ง request ซ้ำเป๊ะ
       ไม่มี feedback ให้โมเดลรู้ว่าผิดตรงไหน — แก้โดยส่ง validation error กลับไปเป็นส่วนหนึ่งของ
       instruction ในรอบ retry (attempt>0 เท่านั้น, cached blocks ไม่กระทบ) เป็น defense-in-depth
       ทั่วไป ไม่ใช่แค่แก้เฉพาะ 2 กลุ่มข้างต้น
  - **ผลลัพธ์หลังแก้ทั้งสามจุด**: รัน `run_eval.py --model claude-opus-5` ผ่านครบทั้ง 3 เอกสาร
    ไม่มี error เลย (จากเดิม 2/3 fail สนิท) ได้ 185/215 exact (86%), wrong 24, missed 0,
    hallucinated 6 — `wrong`/`hallucinated` ส่วนใหญ่กระจุกอยู่ที่ list field
    (`required_documents[]`, `qualifications[]`) ซึ่งน่าจะเป็นเพราะ **scorer เทียบ list แบบ
    positional index-by-index** (ไม่ได้ match เนื้อหา) บวกกับโมเดลอาจตอบมากกว่าที่ ground truth
    คัดไว้ (ground truth เลือกแบบ curated ไม่ใช่ exhaustive) — เป็น known limitation ของ
    `run_eval.py` เอง ไม่ใช่หลักฐานว่าโมเดลตอบผิดจริงเสมอไป **ควรตรวจสอบ required_documents/
    qualifications ที่ scorer บอกว่า wrong ด้วยตาจริงก่อนสรุปว่าคุณภาพแย่**
  - **ค่าใช้จ่ายรวมทั้ง debugging thread นี้**: Haiku sanity ~$0.05 + Opus รอบแรก ~$0.31 +
    Opus verify (เจอบั๊ก key_dates) ~$1.78 + Opus verify สุดท้าย (ผ่านครบ) ~$3.75
    รวมประมาณ **$5.9** ทั้งหมดผ่านการถามยืนยันจากผู้ใช้ก่อนทุกครั้งที่มีนัยสำคัญ

## เซสชันต่อมา: แก้ scoring limitation + ขุดเจอบั๊กเพิ่มอีก 2 จุดจาก Haiku

ผู้ใช้ขอให้ขุด required_documents/qualifications scoring limitation ต่อ พร้อมถามว่าถ้าไม่ใช้
Opus 5 (โมเดลแพง) จะรับมือยังไง — สรุปสิ่งที่ทำและพบ:

- **แก้ scorer**: เปลี่ยนจาก positional index-matching เป็น **content-based greedy matching**
  (`_primary_text` ดึงข้อความตัวแทนของแต่ละ list item, `_similarity` ใช้ substring/bigram
  overlap, จับคู่ similarity สูงสุดก่อน) ใน `run_eval.py` — ทดสอบแล้วว่า reorder + item เกิน
  ไม่ทำให้กลายเป็น "wrong" อีกต่อไป (เดิมเป็นแบบนี้จริง เป็นสาเหตุหลักที่ตัวเลข eval รอบก่อนดูแย่
  เกินจริง) นอกจากนี้เพิ่มการบันทึกผล extraction จริงของแต่ละเอกสารไว้ที่
  `backend/outputs/eval/<sample_id>_<model>.json` เพื่อ audit ย้อนหลังได้โดยไม่ต้องรันซ้ำ
- **ตัดสินใจ**: ไม่ทำ per-group model override (เลือกโมเดลต่างกันต่อ FieldGroup) ตอนนี้ ถึงแม้
  จะเป็นทางแก้ตรงจุดสำหรับคำถาม "ไม่ใช้ Opus จะทำไงกับกลุ่มที่พลาดบ่อย" เพราะจะต้องออกแบบใหม่
  อีกรอบตอนทำ multi-provider (ดูหัวข้อ To-do ทีหลัง ด้านบน) — เก็บไว้เป็น design note ให้ทำ
  พร้อมกันตอนนั้นแทน
- **บั๊กที่ 3 (Haiku เท่านั้น ไม่เกิดกับ Opus)**: `evaluation_criteria.technical_weight` โดน
  โมเดล**อนุมาน**เป็น 0.0 เพราะเอกสารบอกว่าใช้ "หลักเกณฑ์ราคา" (price-only) — ทั้งที่เอกสาร
  ไม่เคยเขียนตัวเลข 0% ไว้จริง (ละเมิดกฎข้อ 1 ห้ามคำนวณ) และ `contact.department` โดนใส่ค่าเป็น
  ประโยคอธิบาย ("ไม่ระบุ...เฉพาะเจาะจง") แทนที่จะเป็น null+reason — เกิดแม้จะมี retry-feedback
  fix แล้วก็ตาม (Haiku ตอบผิดซ้ำ 2 รอบเหมือนเดิม) แก้โดย (1) เพิ่มคำเตือนเฉพาะจุดใน
  `group_misc.md` ทั้งสองฟิลด์ (2) เพิ่ม **worked example ทั่วไป** ใน `extract_system.md`
  อธิบายว่า "การอนุมานเชิงตรรกะจากข้อความเชิงคุณภาพก็ถือเป็นการเดา" — ยืนยันแล้วว่าทั้งสองฟิลด์
  ที่แก้ตรง ๆ หายขาดในรอบถัดไป (0 error, 0 wrong ที่ฟิลด์เหล่านี้)
- **บั๊กที่ 4 (พบหลังแก้บั๊กที่ 3 — pattern เดิมโผล่จุดใหม่)**: `deliverables[].days_from_signing`
  ของ `tor_2733` (เอกสารที่ระบุงวดเป็น "ประจำเดือนตุลาคม 2569" ไม่ใช่ตัวเลขวัน) โดนโมเดล
  **คำนวณ**จำนวนวันเองจากชื่อเดือน (12/12 รายการเป็น hallucinated ทั้งที่ ground truth ตั้งใจ
  ให้เป็น null) — ต้นตอเดียวกับบั๊กที่ 3 เป๊ะ (โมเดลถือว่า "การอนุมานที่ดูสมเหตุสมผล" ไม่ใช่
  "การเดา") แค่โผล่ในฟิลด์ใหม่ที่ยังไม่เคยแก้ตรง ๆ แก้แล้วใน `group_deliverables.md`
  **ยังไม่ได้ verify ด้วย API จริง** (แก้เสร็จแต่ยังไม่รันซ้ำ ประหยัดค่าใช้จ่าย รอรวมกับรอบ
  eval ถัดไป)
- **ข้อสรุปสำคัญสำหรับคำถาม "ไม่ใช้ Opus จะรับมือยังไง"**: การแก้ prompt ทีละจุดตามที่เจอ
  ได้ผลจริงทุกครั้ง (บั๊กที่แก้แล้ว 3/3 หายขาด) แต่ **เป็นการไล่แก้ทีละจุด ไม่ใช่การแก้ที่ต้นตอ
  ทั้งหมดในทีเดียว** — Haiku มีนิสัย "อนุมาน/คำนวณตัวเลขที่ฟังดูสมเหตุสมผล" ที่โผล่ในฟิลด์ใหม่
  เรื่อย ๆ เมื่อทดสอบเอกสารที่หลากหลายขึ้น (พบแล้ว 4 ครั้ง ใน 4 ฟิลด์ต่างกัน จากเอกสารแค่ 3 ฉบับ)
  นี่คือต้นทุนจริงของการใช้โมเดลถูกกว่า Opus — ไม่ใช่บั๊กครั้งเดียวจบ แต่เป็นความเสี่ยงต่อเนื่อง
  ที่ต้องเฝ้าระวังทุกครั้งที่เจอเอกสารแบบใหม่ ควรตัดสินใจ (ในอนาคต ไม่ใช่ตอนนี้) ว่าจะยอมรับ
  ความเสี่ยงนี้เพื่อประหยัดค่า API หรือจะใช้โมเดลแรงกว่า Haiku อย่างน้อยกับกลุ่มที่เคยพลาด
  (qualifications, key_dates, misc, deliverables) — เชื่อมโยงกับ per-group model override
  ที่ตัดสินใจเลื่อนไปทำพร้อม multi-provider แล้วข้างบน
- **ตัวเลขล่าสุดหลังแก้บั๊กที่ 3 (Haiku, ยังไม่รวมบั๊กที่ 4)**: 178/215 exact (83%),
  wrong 16, missed 5, hallucinated 16, **0 error/crash ทั้ง 3 เอกสาร** (จากเดิม fail 2/3
  ก่อนแก้อะไรเลย) ค่าใช้จ่ายรอบนี้ $0.5677
- **ค่าใช้จ่ายสะสมทั้ง eval-debugging thread (Haiku sanity ผ่าน Haiku รอบล่าสุด)**: ประมาณ
  **$6.5** ทั้งหมดผ่านการถามยืนยันจากผู้ใช้ก่อนทุกครั้งที่มีนัยสำคัญ

## To-do ที่ยังไม่ทำ จาก Step 6

- **verify การแก้บั๊กที่ 4 (`deliverables[].days_from_signing`) ด้วย API จริง** — แก้ prompt
  แล้วแต่ยังไม่ได้รันยืนยัน ควรรวมกับรอบ eval ถัดไป (ไม่ต้องรันแยกเพื่อประหยัดค่าใช้จ่าย)
- **ไม่มี automated check จับ font ที่ mislabel แล้วให้ข้อความมั่ว (เคส `post_7000`)** —
  `usable_text_ratio` และ `find_glyph_order_anomalies` ตรวจไม่เจอทั้งคู่ ต้องอ่านตาเปล่า
- **Haiku มีความเสี่ยงต่อเนื่อง**เรื่องอนุมาน/คำนวณตัวเลขที่ไม่ได้เขียนไว้ตรง ๆ ในเอกสาร
  (พบแล้ว 4 ครั้งใน 4 ฟิลด์ต่างกัน แก้ตามที่เจอได้ผลทุกครั้ง แต่ไม่รับประกันว่าจะไม่โผล่ที่
  ฟิลด์ใหม่อีกเมื่อเจอเอกสารหลากหลายขึ้น) — ตัดสินใจว่าจะยอมรับความเสี่ยงนี้ หรือใช้โมเดลแรงกว่า
  เฉพาะกลุ่มเสี่ยง (ผูกกับ per-group model override ที่เลื่อนไปทำพร้อม multi-provider)

## Wrap-up (กำลังทำอยู่)

- **`git log -p | grep sk-ant`**: เช็คแล้ว ไม่พบ API key เลยในประวัติ git ทั้งหมด
  (มีแค่ 2 commit เดิม `f716f69` Initial commit และ `5bb5fff` Update README.md
  เพิ่มแค่ `LICENSE`/`README.md` เท่านั้น ไม่เคยมีโค้ดหรือ `.env` ถูก commit มาก่อนเลย)
- **AGPL/PyMuPDF license — พบปัญหาจริง แก้แล้วตามที่ผู้ใช้ตัดสินใจ**: เช็คจาก
  `pip show pymupdf` โดยตรง (ไม่เดา) ได้ `License: Dual Licensed - GNU AFFERO GPL 3.0 or
  Artifex Commercial License` แต่ `LICENSE` เดิมของ repo เป็น MIT — ขัดกันจริง เพราะ backend
  เป็น network service (FastAPI) ซึ่งเข้าเงื่อนไข AGPL มาตรา 13 (network use) พอดี
  **ผู้ใช้ตัดสินใจ**: เปลี่ยน `LICENSE` เป็น AGPL-3.0 เต็มฉบับ (ดาวน์โหลดตัวเต็มจริงจาก
  `gnu.org/licenses/agpl-3.0.txt` ไม่ได้พิมพ์เองจากความจำ เพราะเป็นเอกสารกฎหมายต้องตรงเป๊ะ)
  **ผลกระทบที่ผู้ใช้ควรรู้ไว้**: AGPL เป็น copyleft แรง ใครเอาไปรันเป็น network service แบบ
  แก้ไขแล้วต้องปล่อยซอร์สส่วนที่แก้ด้วย — ถ้าจะทำเป็น SaaS ปิดซอร์สในอนาคต ต้องซื้อ Artifex
  commercial license แทน หรือเปลี่ยนไปใช้ library อื่นแทน PyMuPDF (ต้องเขียน
  `pdf/extract.py`/`pdf/scanned.py` ใหม่ เพราะใช้ API เฉพาะของ PyMuPDF เยอะ)
- **README.md — เขียนเสร็จแล้ว** (ไทยก่อน อังกฤษต่อท้ายในไฟล์เดียว ตามแผน) ครอบคลุม:
  คุณสมบัติหลัก, ข้อจำกัด v0.1 (ไม่มี OCR, ไฮไลต์ best-effort, cache ข้ามกลุ่มใช้ไม่ได้,
  ความเสี่ยงเรื่องโมเดลถูกอนุมานค่าเอง, ยังไม่รองรับ provider อื่น), วิธีติดตั้ง/รัน,
  environment variables, API endpoints (`/api/health`, `/api/extract`, `/api/export/csv`
  — ตรวจจาก source code จริงแล้ว), CLI, การประเมินผล (พร้อมตัวเลขล่าสุด 185/215), license
  พร้อมคำอธิบาย AGPL/PyMuPDF อย่างละเอียด
- **หมายเหตุ**: `docker-compose.yml` ปัจจุบันมีแค่ service `backend` เท่านั้น ไม่มี frontend
  service — README เขียนให้ตรงกับของจริงแล้ว (บอกให้รัน `npm run dev` แยก ไม่ใช่
  one-command full-stack startup)

- **พบ+แก้ repo hygiene bug เก่าก่อน commit**: `backend/app/derive/`, `backend/app/llm/`,
  `backend/app/models/` ไม่มี `__init__.py` ที่ตำแหน่งถูกต้องมาตั้งแต่ก่อนเซสชันนี้ (มีแต่
  สำเนาเปล่าที่ผิดที่ `backend/backend/app/...` — เดาว่าเกิดจาก path ผิดตอนสร้างไฟล์ในเซสชัน
  ก่อนหน้า) โค้ดทำงานได้ตลอดเพราะ Python ถือเป็น implicit namespace package แทน — สร้าง
  `__init__.py` เปล่าที่ตำแหน่งถูกต้องให้ครบ (ตรงกับ pattern ของ `app/pdf`, `app/thai` ฯลฯ)
  แล้วลบ `backend/backend/` ทิ้ง ยืนยันด้วย `pytest` ผ่านครบ 42 tests เหมือนเดิม (no-op
  ทางพฤติกรรม เพราะเป็นไฟล์เปล่าทั้งคู่)

## ขั้นต่อไปถ้าเซสชันนี้ขาดไป

Wrap-up ทำครบทุกข้อแล้ว (secret check, license, README, repo hygiene fix) — เหลือแค่ผ่าน
`/quick-commit` (ห้าม commit ตรงเองเด็ดขาดตาม CLAUDE.md ของผู้ใช้) เพื่อ commit งานทั้งหมด
ของเซสชันนี้เป็นครั้งแรกจริง ๆ (ทุกอย่างยัง uncommitted อยู่จนถึงตอนนี้)

## To-do ทีหลัง (ยังไม่ทำใน v0.1)

- **Multi-provider support** (OpenAI/GPT, Gemini, Llama, Qwen ฯลฯ นอกจาก Claude) — ผู้ใช้ถามแล้ว
  ตัดสินใจเลื่อนไปทำทีหลัง ไม่บล็อก Step 6 เพราะเป็นงานสถาปัตยกรรมจริง ไม่ใช่แค่เปลี่ยน env var:
  1. `output_format=group.schema` ใน `llm/client.py` เป็น structured-output ของ Anthropic โดยเฉพาะ
     (`response.parsed_output`) — provider อื่นมี mechanism ต่างกัน (บาง provider ไม่มีเลย)
  2. prompt caching (`cache_control: ephemeral`, `cache_creation_input_tokens`,
     `cache_read_input_tokens`) เป็น API surface เฉพาะของ Anthropic — ผูกกับสูตรคำนวณราคาใน
     `pricing.py` ด้วย
  3. การแตกเป็น 6 FieldGroup ใน `groups.py` มาจาก limit เฉพาะของ Anthropic ("compiled grammar
     too large") — provider อื่นน่าจะมี limit ที่จุดต่างกัน ต้องวัดใหม่แยกต่างหาก
  ถ้าจะทำจริง: ต้องมี provider-abstraction layer + ตารางราคาต่อ provider + วัด/ปรับ group split
  ใหม่ทีละ provider
  - **หมายเหตุจาก Step 6 eval**: เจอ evidence จริงว่า Haiku ละเมิดกฎ rule #1/#2/#3
    (ห้ามเดา/ต้องมี source/null+reason) ในจุดที่ Opus ไม่พลาด — เกิดคนละจุดคนละกลุ่ม 3 ครั้งแล้ว
    (qualifications, key_dates, misc) เมื่อออกแบบ multi-provider ควรทำ **per-group model
    override** ไปพร้อมกันเลย (ให้ `FieldGroup` เลือก provider+model ของตัวเองได้ ไม่ใช่ตายตัว
    ทั้งเอกสาร) จะได้ใช้โมเดลถูก ๆ กับกลุ่มที่ตรงไปตรงมา (basic_info, bonds, deliverables)
    และโมเดลแรงกว่ากับกลุ่มที่พบว่าพลาดบ่อย (qualifications, key_dates, misc) โดยไม่ต้องจ่าย
    ราคา Opus ทั้งเอกสาร — **ตัดสินใจแล้วว่าจะไม่ทำ per-group override แยกสำหรับ Anthropic
    อย่างเดียวตอนนี้ เพราะจะต้องออกแบบใหม่อีกรอบตอนทำ multi-provider จริง ทำครั้งเดียวตอนนั้นดีกว่า**

## อื่น ๆ ที่ทำในเซสชันนี้

- แปล comment ที่เป็นภาษาไทยในโค้ด (docstring ที่ quote หัวข้อ plan) เป็นอังกฤษ:
  `.env.example`, `backend/app/derive/pricing.py`, `backend/app/pdf/extract.py`
  **ไม่แตะ**: enum literal, dict คำเลขไทย, ข้อความ error/CLI output ที่เป็น user-facing จริง,
  prompt ที่ส่งให้ Claude, UI text ใน frontend — ทั้งหมดนี้เป็น data/behavior ไม่ใช่ comment

## ข้อเท็จจริงสำคัญที่ต้องรู้ก่อนแตะโค้ดต่อ

- **โมเดลที่ใช้ตอนพัฒนา: `claude-haiku-4-5`** (ผู้ใช้ขอให้ใช้ตัวนี้ตอน dev, เก็บ Opus 5
  ไว้ตอนรัน eval จริงตามแผนเดิม)
- Backend ใช้ Python 3.9 ในเครื่อง (venv ที่ `backend/.venv`) ต้องมี `eval_type_backport`
  ถึงจะรัน `X | None` syntax ได้ — **นี่คือ workaround เฉพาะเครื่อง dev เท่านั้น**
  Docker ใช้ Python 3.12 จริง ไม่ต้องพึ่ง backport นี้ (ไม่ได้อยู่ใน `pyproject.toml` dependencies)
- Root `.env` มี API key จริงของผู้ใช้ — **ห้าม `cat`/`Read` ไฟล์นี้ทั้งไฟล์** ถ้าจะเช็คตัวแปร
  ให้ใช้ `grep -v ANTHROPIC_API_KEY .env` หรือ `grep "^KEY_NAME=" .env` แทน
- schema (`backend/app/models/schema.py`) เป็น single source of truth ที่ frontend
  (`frontend/src/types/schema.ts`) มือก๊อบตามไว้ **ไม่มี codegen** — แก้ schema.py แล้วต้องแก้
  schema.ts เองด้วยมือเสมอ
- `Source` ไม่มี bbox เลย (มีแค่ `page` + `quote`) — PDF highlight ใน `PdfViewer.tsx`
  ใช้วิธี text-matching กับ text layer ของ pdf.js ไม่ใช่ bbox coordinate — เป็น best-effort
  ตามที่ตกลงกับผู้ใช้ตอนเลือก react-pdf

## เซสชันใหม่: Multi-provider migration (2026-09-02, ต่อจาก to-do ข้างบน)

ผู้ใช้ขอให้ทำ multi-provider migration ตามที่ deferred ไว้ข้างบน — เขียนแผนละเอียดที่
`docs/plans/2026-09-02-multi-provider-migration.md` (9 tasks) แล้วทำจริงทีละ task
(inline ในเซสชันนี้ ไม่ใช้ subagent) ตาม TDD ทุก step — checkbox ในไฟล์แผนอัปเดตตามจริงเสมอ
(`[x]` เสร็จจริง, `[~]` เสร็จบางส่วนมี note, `[ ]` ยังไม่ทำ) **ให้เชื่อ checkbox ในไฟล์แผน
มากกว่าสรุปด้านล่างนี้ถ้าขัดกัน เพราะแผนคือของจริงที่อัปเดตทุกครั้ง**

### Task 1-5: เสร็จสมบูรณ์ ยืนยันแล้วด้วย live call จริง

- สร้าง `LLMProvider` port (`backend/app/llm/providers/base.py`) — `client.py` ไม่ import
  vendor SDK ตรงเองอีกแล้ว คุยผ่าน interface เดียว (`complete_structured`)
- `AnthropicProvider` + `registry.py` (capability gate — ปฏิเสธ provider ที่ไม่มี native
  structured output ตอน construct ไม่ใช่ตอน extract กลางทาง)
- pricing table เปลี่ยนจาก key ด้วย model เดียว เป็น `(provider, model)` คู่ (bare model id
  ไม่ unique ข้าม provider จริง ๆ)
- **Breaking API change ที่ตั้งใจทำ**: `cache_creation_input_tokens`/`cache_read_input_tokens`
  (ชื่อ Anthropic) เปลี่ยนเป็น `cache_write_tokens`/`cached_read_tokens` (ชื่อ neutral) ทั้ง
  `schema.py`, `types/schema.ts`, `UsageFooter.tsx` พร้อมกันในคอมมิตเดียว
- Per-group provider/model override (`TOR_GROUP_<GROUP>=<provider>:<model>`) — ตามที่ deferred
  ไว้จากเซสชันก่อน ทำพร้อม multi-provider จริงตามที่ตัดสินใจไว้
- **บั๊กจริงที่เจอระหว่างทำ (ไม่ใช่ที่คาดไว้ในแผน)**:
  1. Python 3.9 ไม่รองรับ `X | None` ใน module-level type alias ที่เป็น runtime expression
     (ไม่ใช่ deferred annotation) แม้มี `from __future__ import annotations` — แก้ด้วย
     `typing.Optional[str]`
  2. ลืมแก้ field rename ตกที่ `run_extraction.py` (พบตอนรัน live call จริง เงินเสียไปแล้ว
     แต่ JSON ถูก save ไว้ก่อน crash เลยไม่ต้องรันซ้ำ) และ **ลืมอีกครั้งที่ `run_eval.py`**
     (บั๊ก class เดียวกัน rewrite เดียวกัน — grep ทั้ง repo หาที่เหลือแล้ว ไม่มีแล้ว)
- ยืนยัน live กับ `claude-haiku-4-5` จริง ตรงกับ ground truth เดิม ($0.0478)

### Task 6 (OpenAI): สร้างเสร็จ ติด billing บล็อก

- OpenAI **ไม่มี free tier** สำหรับ API (เช็คจาก pricing page จริง มีแค่
  `omni-moderation-latest` ที่ฟรี ซึ่งเป็น moderation model ใช้กับงานนี้ไม่ได้)
- Adapter เขียนโดย static introspection ของ SDK ที่ลงจริง (openai==2.48.0) ไม่เดาจากความจำ
  ยืนยันได้ทุกอย่างที่ต้องรู้ (`.parse()`, field names) ยกเว้นพฤติกรรม runtime จริง
- ติดที่ account ไม่มี credit (`insufficient_quota`) — ยังไม่ได้รัน eval gate จริง

### Task 7 (Gemini): สร้างเสร็จ ยืนยัน live แล้ว 2/3 เอกสาร

- Gemini **มี free tier จริง** (ตรงข้ามกับ OpenAI) แต่จำกัด 20 requests/day ต่อโมเดล
- **บั๊กจริงที่เจอจาก live call (สำคัญ)**: `gemini-3.6-flash` เป็น thinking model —
  `thoughts_token_count` กิน 65-72% ของ token ทั้งหมด แต่ตอนแรกไม่ได้เอามารวมใน
  `output_tokens` เลย — ถ้าไม่แก้จะรายงานค่าใช้จ่ายผิดเกินครึ่ง ยืนยันจาก Google pricing page
  จริงว่า thinking token คิดราคาเท่า output ธรรมดา แก้แล้ว
- `gemini-2.5-flash` (ที่เขียนไว้ในแผน) **เลิกให้บริการแล้วสำหรับ user ใหม่** — API เองส่ง 404
  พร้อมชี้ตัวแทนที่ถูก (`gemini-3.6-flash`) — บทเรียน: ห้ามเชื่อชื่อโมเดลที่จำมา ต้องเช็คจาก
  API จริงเสมอ
- รัน eval gate ได้ 2/3 เอกสาร (audit_26394_bidding, tor_2400) ก่อนชน free-tier quota —
  **112/127 field ตรงเป๊ะ (88%), missed 0, crash 0** — `deliverables[].days_from_signing`
  ได้ 12/12 ตรงเป๊ะ (จุดที่ Haiku เคย hallucinate คำนวณเองมาก่อนในเซสชันก่อน) เอกสารที่ 3
  (tor_2733) รอ quota reset หรือ paid tier

### Task 8 (openai_compat / self-hosted): สร้างเสร็จ ยืนยัน live กับ Groq จริง — เจอบั๊กมากที่สุด

ทดสอบกับ Groq (`openai/gpt-oss-120b`, reasoning model) เพราะผู้ใช้มี key อยู่แล้ว ไม่ได้ลง
Ollama local เจอบั๊กจริง **3 ตัว** ระหว่างพยายามให้ live call ผ่าน:

1. `get_provider()` ไม่ได้ส่ง model ตัวจริงเข้าไปให้ capability probe ของ `openai_compat`
   ใช้ — probe เลยยิงด้วย model name `"unknown"` ที่ไม่มีจริง (404) ต้องแก้ signature ของ
   `get_provider()` และ `provider_for` (`client.py` + ทั้ง 3 caller) ให้ส่ง model ไปด้วย
   ไม่ใช่แค่ provider name
2. OpenAI-compatible strict mode ต้องการ transform เพิ่มจาก `model_json_schema()` เปล่า ๆ
   2 อย่าง: `additionalProperties: false` ทุก object node (รวมใน `$defs`) และทุก key ใน
   `properties` ต้องอยู่ใน `required` ด้วย (field ที่ optional ของเราใช้ nullable type
   อยู่แล้ว ใส่ required เพิ่มไม่ทำให้ผิดหลักอะไร) — `openai` SDK จริงทำให้อัตโนมัติผ่าน
   `.parse()` แต่ endpoint ทั่วไปไม่ได้ผ่าน SDK นั้น ต้องทำเองใน `_make_strict_json_schema()`
   ยืนยันด้วย script ตรวจทั้ง schema ก่อนยิงจริงซ้ำ (ประหยัดเงิน)
3. probe เดิมใช้ `max_tokens=64` สำหรับ schema ง่าย ๆ `{ok: bool}` แต่ reasoning model กิน
   token ไปกับการ "คิด" ก่อนตอบเสมอ (แม้คำตอบสั้นมาก) — ยืนยันจริงว่าตอบแค่ `{"ok":true}`
   ก็ใช้ไป 74 token แล้ว แก้เป็น 1000
- หลังแก้ทั้ง 3 จุด probe ผ่านสำเร็จ (พิสูจน์ adapter design ถูกต้องจริงกับ endpoint จริง
  ไม่ใช่แค่ unit test) แต่กลุ่ม `misc` (5 field) ชน `MAX_TOKENS=8000` เพราะโมเดลนี้ reasoning
  ยาวมาก (เห็น `failed_generation` เป็น chain-of-thought ยาวที่ไม่จบ ไม่ใช่ schema ผิด)
  **ตัดสินใจไม่ขยับ `MAX_TOKENS` ทั้งระบบ** เพราะไม่มีหลักฐานว่า Anthropic/OpenAI ต้องการ
  บันทึกไว้เป็น known limitation ใน `client.py` แทน — ผู้ใช้เลือกหยุดตรงนี้ไม่ไล่ retry ต่อ

### สถานะรวมล่าสุด

Task 1-5 เสร็จสมบูรณ์ 100%. Task 6-8 (OpenAI/Gemini/openai_compat) มี adapter ที่สร้าง+test
ผ่านหมดแล้ว แต่ eval gate เต็มรูปแบบยังไม่ผ่านครบทุก provider (ติด account/quota ไม่ใช่โค้ด)
Task 9 (cross-provider comparison report) ยังไม่เริ่ม — ดู checkbox ในไฟล์แผนเพื่อความแม่นยำ

**ค่าใช้จ่ายจริงที่เกิดขึ้นในเซสชันนี้**: Anthropic live check เล็กน้อย (~$0.05), Gemini/OpenAI-
compat ทดสอบทั้งหมดผ่าน free tier (Gemini) หรือ credit ที่มีอยู่แล้ว (Groq) — ไม่มีการเสีย
เงินก้อนใหญ่โดยไม่ถามก่อน ทุกจุดที่มีนัยสำคัญถามผู้ใช้ก่อนเสมอ

## Task 9 (cross-provider comparison report): เสร็จ พบ limitation ที่ 3 ของ Groq/gpt-oss-120b

สร้าง `backend/app/eval/compare_providers.py` (2 โหมด: `--check-schema-ceiling`,
`--eval`) — พบบั๊ก/finding จริงหลายจุดระหว่างรัน ไม่ใช่แค่เขียนโค้ดผ่าน:

- **บั๊กในเครื่องมือของตัวเอง**: `_CEILING_CHECK_MAX_TOKENS` เดิมตั้งไว้ 512 ต่ำเกินไป
  ทำให้ `anthropic` (โมเดลที่ไม่ reasoning) ตอบไม่ทันสำหรับ 3/6 กลุ่ม (basic_info, bonds,
  misc) เพราะ stub document ว่างเปล่าก็ยังต้องเขียน reason ให้ทุก field ที่เป็น null
  ยิ่งกลุ่มมี field เยอะยิ่งใช้ token เยอะ ไม่เกี่ยวกับ schema ซับซ้อนเลย — แก้เป็น 3000
  ยืนยันว่า `anthropic` ผ่านครบ 6/6 กลุ่มหลังแก้ (ตรงกับที่ระบบจริงใช้ MAX_TOKENS=8000 อยู่แล้ว)
- **Finding ที่ 2 ของ `openai/gpt-oss-120b` (ต่างจาก reasoning-budget ที่เจอใน Task 8)**:
  แม้ budget พอแล้ว (3000) กลุ่ม `bonds`/`misc` ยังพัง แต่ครั้งนี้เป็นเพราะโมเดลตอบ
  `"reason": null` แทนที่จะเป็นข้อความจริง — ผ่าน JSON schema ได้ (เพราะ required บอกแค่ว่า
  key ต้องมี ไม่ได้บอกว่าห้าม null) แต่ผิดกฎ #3 ของโปรเจกต์ (null ต้องมี reason จริง)
  — เป็นช่องว่างเชิงโครงสร้างจริงระหว่าง JSON-schema-level enforcement กับ Pydantic
  custom validator ของเรา ไม่ใช่สิ่งที่ "แก้" ที่ adapter ได้ เป็นข้อมูลเปรียบเทียบจริงที่
  เครื่องมือนี้มีไว้เพื่อหาสิ่งนี้เลย
- **Finding ที่ 3 ของ `openai/gpt-oss-120b`**: รัน `--eval` เต็มรูปแบบ (3 เอกสารจริง) —
  เอกสารสั้น (`tor_2400`) ผ่าน แต่เอกสารยาว 2 ฉบับ (`audit_26394_bidding`, `tor_2733`)
  โดน Groq ปฏิเสธด้วย 413 rate_limit_exceeded: on-demand tier จำกัด **8000 token/นาที**
  แต่ input ของเอกสารพวกนี้ (shared rules + เนื้อเอกสาร + schema) ต้องใช้ 16,486-17,060
  token ต่อ request เดียว เกิน limit ไปมาก — ไม่ใช่บั๊กโค้ด เป็น account tier limit จริง
  (error message ของ Groq เองแนะนำให้ upgrade เป็น Dev Tier)
- **ผลเปรียบเทียบสุดท้าย** (ตาราง markdown เต็มอยู่ใน `docs/plans/2026-09-02-multi-provider-
  migration.md` Task 9):

  | Provider/Model | Exact | Wrong | Missed | Hallucinated | Crashed docs | Cost |
  |---|---|---|---|---|---|---|
  | anthropic/claude-haiku-4-5 | 195 | 15 | 2 | 3 | none | $0.6177 |
  | openai_compat/openai-gpt-oss-120b | 26 | 0 | 2 | 1 | audit_26394_bidding, tor_2733 | unknown |

  Anthropic ผ่านครบ 3 เอกสารไม่มี crash เลย 195/215 ตรงเป๊ะ (91%) — ดีกว่า baseline เดิม
  (178/215 ตอน Step 6) เพราะสะสมการแก้ prompt จากหลาย session ก่อนหน้า
- อัปเดต `README.md` ทั้งสองภาษา: แก้คำที่ผิดแล้ว ("ยังไม่รองรับ provider อื่น" — ตอนนี้รองรับ
  แล้วจริง ผ่าน unit test ครบ แต่ eval เต็มรูปแบบยังผ่านแค่ anthropic) เพิ่มตาราง env var
  สำหรับ provider ใหม่ทั้งหมด และย่อหน้าสรุปผล cross-provider comparison
- **OPENAI_API_KEY/GEMINI_API_KEY หายจาก `.env` ระหว่างเซสชัน** (ผู้ใช้ลบเองหลัง Task 6-7)
  ทำให้ Task 9 เทียบได้แค่ anthropic + openai_compat เท่านั้น — ถ้าจะเทียบ OpenAI/Gemini
  ด้วย ต้องเติม key กลับก่อน

### สถานะรวม Task 1-9 (ล่าสุดสุด)

Task 1-5, 9 เสร็จสมบูรณ์. Task 6-8 มี adapter สร้าง+unit test ผ่านครบ แต่ eval เต็มรูปแบบ
ยังไม่ผ่านทุก provider (ติด billing/quota ของ account ทดสอบเอง ไม่ใช่โค้ด) — ดู checkbox
ในไฟล์แผนเพื่อความแม่นยำที่สุดเสมอ งานทั้งหมดอยู่ระหว่างตัดสินใจว่าจะ commit ต่อหรือยัง

## เซสชันใหม่: Multi-format ingestion — สแกน PDF (vision OCR), DOCX, XLSX (2026-09-03)

แผนเต็มอยู่ที่ `~/.claude/plans/valiant-booping-sloth.md`. โจทย์: ผู้ใช้อยากให้รองรับ (1)
PDF ที่เป็นภาพสแกนล้วน (ไม่มี text layer) และ (2) ไฟล์ Word/Excel นอกจาก PDF ตรวจสอบก่อนแล้วว่า
ไม่มีแผนเก่าเรื่องนี้อยู่เลยในโปรเจกต์ (README/CLAUDE.md แค่บอกว่า "ยังไม่มี OCR" เป็นข้อจำกัด
ไม่ใช่ของที่วางแผนไว้แล้ว) แบ่งเป็น 5 phase ทำสำเร็จครบทั้งหมด ตามลำดับ: **Source ให้ยืดหยุ่นก่อน
(behavior-preserving) -> ingest abstraction บน PDF เดิม -> XLSX -> DOCX -> vision OCR** เหตุผลของ
ลำดับนี้คือให้ของที่เสี่ยงเปลี่ยนแปลงเยอะที่สุดแต่ไม่เปลี่ยน behavior จริงมาก่อน แล้วค่อยเพิ่มความ
ซับซ้อนทีละอย่าง จบที่ของที่แตะทุก provider adapter พร้อมกัน (เสี่ยงสุด)

### การตัดสินใจหลักที่ผู้ใช้เลือก (ก่อนเริ่มเขียนโค้ด)

1. **OCR ใช้ vision LLM ไม่ใช่ OCR แบบเดิม** (ไม่ใช้ pytesseract/cloud OCR API) — render หน้าที่
   สแกนเป็นภาพ (PyMuPDF ทำได้ในตัว) แล้วส่งผ่าน pipeline multi-provider ที่มีอยู่แล้ว
2. **Source ต้องยืดหยุ่นกว่าแค่ "page"** — DOCX/XLSX ไม่มีเลขหน้าจริง (Word แบ่งหน้าตอน render
   ไม่ใช่ข้อมูลที่เก็บในไฟล์; Excel มี cell ไม่มีหน้า)
3. **ทำเป็นแผนเดียว ต่อเนื่องกันทั้ง 3 รูปแบบ** ไม่แยกแผนย่อย

### Phase 1 — Source generalization: พบว่าสมมติฐานของแผนผิด แต่แก้ได้เร็วเพราะวัดจริงก่อนเปลี่ยน

ออกแบบ `Source` ใหม่ให้มี `kind` (`text_page`/`vision_page`/`paragraph`/`table_cell_docx`/
`cell_xlsx`) ตอนแรกให้แต่ละ kind มี field ตำแหน่งของตัวเอง (8 field รวม: page, paragraph_index,
heading_path, table_index/row/col, sheet, cell) — **live test จริงบน `claude-haiku-4-5` ล้มทันที**
ที่กลุ่ม `misc`: `400 Schema is too complex for compilation` เพราะ `Source` ถูกอ้างอิงใน
`Sourced[T]` ทุก leaf (~26 จุด) การเพิ่ม field เข้าไปคูณเข้ากับทุกจุดที่อ้างอิง

วัด byte ของ JSON schema จริงก่อนแก้ (ไม่เดา): schema เดิม 3,789 bytes (`misc`, ผ่าน) ->
8-field ใหม่ 5,899 bytes (ไม่ผ่าน) หลังผู้ใช้เลือก **ยุบเหลือ `page` + `ref` string เดียว**
(`"para:12"`, `"t1:r3:c2"`, `"Sheet1!B5"`, regex-validate ตาม kind) ยังได้ 5,518 bytes — เกิน
คาดเพราะ **สาเหตุจริงไม่ใช่จำนวน field แต่คือ docstring ของ class `Source`** (Pydantic ส่ง
docstring เข้า JSON schema เป็น `description` field, 1.4KB ของ docstring ซ้ำในทุก group schema
ที่อ้างอิง `Source`) ย้าย docstring ยาวไปเป็น `#` comment (ไม่เข้า schema) เหลือ 4,142 bytes —
ผ่านสบาย ทุก group ตอนนี้ ~+353 bytes จาก baseline เท่านั้น **บทเรียนสำคัญ**: model ที่ถูกอ้างอิง
จากหลาย leaf ต้องระวัง docstring ยาว ไม่ใช่แค่จำนวน field — บันทึกไว้ใน `CLAUDE.md` เป็น trap ใหม่

Live verify (haiku, 1 หน้า, $0.0658): โมเดลตอบ `kind="text_page"` ถูกทุกจุด (10/10 source),
`ref: null` เสมอ, ไม่มี violation เลย eval ground truth เก่ายังใช้ scoring ได้ (แค่ shape stale
ไม่ invalid) เพราะ scorer เช็คแค่ key set `{value,source,confidence,reason}` ไม่แตะข้างในของ
`source` เลย — ยืนยันจาก docstring ของ `run_eval.py` เอง

### Phase 2 — ingest abstraction บน PDF เดิม: พิสูจน์ inert ด้วยวิธีที่ดีกว่าที่แผนขอ

สร้าง `backend/app/ingest/{base,detect,pdf_ingest}.py` เป็น facade บน `app/pdf/*` เดิม (ไม่แก้
ของเดิมเลย) แผนขอให้รัน eval 3 เอกสารจริง (~$0.62) เพื่อพิสูจน์ว่า refactor ไม่เปลี่ยน behavior
— **เลือกไม่รันของจริง** ใช้วิธีที่แน่นอนกว่าและฟรีแทน: เทียบ `document_text` แบบ byte-ต่อ-byte
ระหว่างของเก่ากับ facade ใหม่บน sample จริงทั้ง 6 ไฟล์ **เหมือนกันทุก byte ทุกไฟล์** รวมถึง
`post_8000.pdf` ที่เป็นไฟล์สแกนล้วน (0 byte text) — เจอไฟล์นี้ตอนทดสอบ กลายเป็น fixture ที่มีค่า
มากสำหรับ Phase 5 ในตัว (ในเครื่องอยู่แล้ว ไม่ต้องพึ่งไฟล์นอก repo)

### Phase 3 — XLSX: สร้างเสร็จ แต่ปิดไว้เพราะหลักฐานจริงจากผู้ใช้

ทำ `xlsx_ingest.py` ด้วย `openpyxl` (MIT, ตรวจสอบกับ PyPI ก่อนเพิ่ม) จุดสำคัญ: ใช้
`load_workbook(data_only=True)` อ่านค่า formula ที่ Excel cache ไว้แล้วเท่านั้น **ไม่คำนวณ formula
เอง** (ตรงกับกฎข้อ 1 — cell สูตรที่ไม่มีค่า cache จะหายไปจาก prompt โมเดลจะตอบ null+reason แทน
การเดา ยืนยันด้วย unit test) ตอนจะ verify live ผู้ใช้บอกว่า **หา TOR ไทยจริงเป็น .xlsx ไม่เจอเลย**
(TOR จริงออกจาก e-GP เป็น PDF หรือร่างเป็น DOCX; Excel ที่เจอในงานจัดซื้อจัดจ้างมักเป็นไฟล์แนบ
เช่น BOQ/ราคากลาง ซึ่งเนื้อหาไม่ตรงกับ schema ของเครื่องมือนี้เลย) — **ตัดสินใจเก็บโค้ดไว้แต่ปิด
ฟีเจอร์** ด้วย env flag `TOR_ENABLE_XLSX` (default off) ไม่ลบทิ้งเพราะพิสูจน์แล้วว่า ingest layer
ใช้ได้จริงกับ format ที่ไม่ใช่ PDF ซึ่งลดความเสี่ยงของ DOCX/vision ที่ตามมา **ไม่เคย live-verify
XLSX เลย** — บันทึกไว้ชัดเจนใน docstring/`.env.example`/test ว่านี่คือ "built, not verified"

### Phase 4 — DOCX: ผู้ใช้ให้เอกสารจริง สมมติฐานของแผนผิดอีกครั้ง แต่ในทางที่ปลอดภัยกว่า

ผู้ใช้ให้ไฟล์จริง (`TOR จ้างธุรการกองช่าง อบต.ตะกั่วป่า .docx`) วิเคราะห์โครงสร้างก่อนเขียนโค้ด
ด้วย stdlib `zipfile`/`ElementTree` (ไม่เสียเงิน ไม่ต้องรอ dependency): พบว่า **134 ย่อหน้า มี
ตารางแค่ 1 ตาราง** — ตรงข้ามกับที่แผนคาดไว้ ("ข้อมูล TOR อยู่ในตารางเป็นหลัก") และ **ไม่มี Word
heading style เลย** (ทุกย่อหน้าใช้ style `a7` หรือไม่มี style) เลขหัวข้อ (`1. ความเป็นมา`,
`3.3 มีวุฒิ...`) พิมพ์เป็นข้อความธรรมดา ไม่ใช่ heading จริง — จึง **ไม่ทำ `heading_path` เลย**
(เดิมแผนจะใช้ style เป็นตัวสร้าง heading hierarchy แต่ไม่มีอะไรให้ใช้จริง) เอกสารยังมีเลขผสม
ระบบ (`3๐` = เลขอารบิก 3 + เลขไทย ๐ = 30 จริง ๆ) ใช้ `normalize_text` เดิม (ตัวเดียวกับ PDF path)
แก้ให้ฟรีเพราะรองรับเลขไทยอยู่แล้ว

จุดยากจริงที่ยืนยันจากเอกสารจริง: `python-docx`'s `document.paragraphs` **ไม่รวมข้อความในตาราง
เลย** และไม่มี unified document-order view — ต้องเดินตาม `document.element.body`'s XML children
เอง แยก `w:p`/`w:tbl` ทีละตัว ตารางเดียวในเอกสารจริงเก็บงาน/ตัวชี้วัด (deliverables) ไว้ — ถ้าใช้
`document.paragraphs` เฉย ๆ จะพลาดข้อมูลนี้ไปเงียบ ๆ (silent data loss ที่แย่ที่สุดสำหรับเครื่องมือนี้)

Live verify (haiku, เอกสารจริง 101 ย่อหน้า, $0.1322): **32 source ทั้งหมดเป็น `paragraph`**
(เอกสารนี้ไม่มีค่าจาก table cell เลยเพราะ deliverables ในตารางเป็น work-measurement ไม่ใช่
field ที่ schema สกัด) — ตรวจสอบ ref ทุกอันที่โมเดลอ้าง **มีอยู่จริงใน document ที่ส่งไป 100%**
(ไม่มี hallucinated ref เลย) `table_cell_docx` ยังไม่เคย live-verify (เอกสารนี้ไม่มีค่าจากตาราง
ให้ทดสอบ) — บันทึกไว้เป็นข้อจำกัดของหลักฐานที่มี ไม่ใช่ว่าโค้ดผิด

### Phase 5 — vision OCR: เจอบั๊กจริง 3 ตัวจาก live evidence ล้วน ไม่มีการเดาเลยสักจุด

เพิ่ม `ImageBlock` + `ProviderCapabilities.vision_input` ใน `base.py`, ต่อสาย vision เข้าทั้ง 4
adapter (Anthropic/OpenAI/Gemini เปิด `vision_input=True` ตรง ๆ, `openai_compat` ปิดไว้เป็น
default เพราะ **probe อัตโนมัติแบบที่ใช้กับ structured-output ใช้ไม่ได้กับ vision** — endpoint ที่
เพิกเฉยต่อภาพแล้วตอบจาก caption text อย่างเดียวจะได้ผลลัพธ์ที่ valid ตาม schema เป๊ะ ตรวจจับด้วย
probe ไม่ได้เลย ต้องเปิดเองด้วย `TOR_OPENAI_COMPAT_VISION=1`) capability check ทำใน
`client.py:extract()` เป็น pre-flight ก่อนรันกลุ่มไหนเลย เพราะ per-group override
(`TOR_GROUP_<NAME>`) อาจชี้ไป provider อื่นที่ไม่รองรับ vision — เช็คทุก group ที่ resolve แล้ว
ก่อน ไม่ใช่แค่ provider default

**บั๊กจริง 3 ตัว เจอทีละตัวจาก live call กับเอกสารสแกนจริงของผู้ใช้ (16 หน้า จาก e-GP)**:

1. **PNG ที่ 200 DPI ใหญ่เกิน**: เอกสาร 16 หน้าจริง render เป็น PNG ได้ ~55MB (base64) —
   Anthropic ตอบ `413 Request exceeds the maximum size` ก่อนเช็ค API key ด้วยซ้ำ วัดจริงก่อน
   ตัดสินใจ (ไม่เดา): เทียบ PNG vs JPEG ที่ DPI ต่าง ๆ พบว่า JPEG ที่ 150 DPI/quality 70 เหลือ
   แค่ ~5.5MB (JPEG เหมาะกับภาพสแกนที่มี noise แบบภาพถ่าย มากกว่า PNG ที่ lossless) ผู้ใช้เลือก
   ตัวเลขนี้เอง เพิ่ม `MAX_VISION_PAYLOAD_BYTES` เป็น safety net อีกชั้น (page count อย่างเดียว
   ไม่พอ เพราะ 16 หน้ายังอยู่ใต้ `MAX_VISION_PAGES=20` แต่ byte เกินไปแล้ว)
2. **`run_extraction.py` มี blanket-reject เดิมซ้ำอยู่**: ลบ check "สแกน = ปฏิเสธ 422" ออกจาก
   `api/extract.py` แล้ว แต่ลืมว่า `run_extraction.py` (CLI) มี copy ของ check เดียวกันแยกอยู่ —
   เจอจาก error message เก่าที่ CLI print ออกมาตรง ๆ ("ไม่รองรับใน v0.1 ไม่มี OCR") ทั้งที่โค้ด
   ที่แก้แล้วบอกว่ารองรับ — แก้ทันทีเพราะ root cause ชัดจากข้อความ ไม่ต้องเดา
3. **Anthropic ปฏิเสธ system block ว่างเปล่า**: เอกสารสแกนล้วน `document_text` เป็น `""` จริง
   (ไม่เคยเกิดมาก่อน Phase 5 เพราะ blanket reject เดิมกันไว้ก่อนถึงจุดนี้เสมอ) พยายามแก้ 2 รอบ:
   รอบแรกเอา `cache_control` ออกจาก block ว่าง (error เปลี่ยนจาก "cache_control cannot be set
   for empty blocks" เป็น "text content blocks must be non-empty" — เผยว่าปัญหาจริงกว้างกว่านั้น)
   รอบสองกรอง block ว่างออกจาก `system` list ทั้งหมด — ผ่าน ทั้ง 2 รอบยืนยันจาก error message
   ของ Anthropic เองตรง ๆ ไม่มีการเดาเลย

Live verify สุดท้าย (haiku, เอกสารสแกนจริง 16 หน้า, **$0.2630**): extraction ผ่านครบ **34 source
ทั้งหมดเป็น `vision_page`** ไม่มี violation เลย หน้าที่อ้างกระจายทั่วเอกสาร (2,3,6,7,8,14 — ไม่ใช่
หน้า 1 ซ้ำ ๆ พิสูจน์ว่าโมเดลอ่านภาพจริงแต่ละหน้า) `budget_amount: 14400000.0` ตรงกับ quote
"๑๔,๔๐๐,๐๐๐.๐๐ บาท" เป๊ะ — พบ quote ที่อ่านผิดเล็กน้อย ("กรมบัญชีศึกษา" น่าจะเป็น "กรมบัญชีกลาง")
ซึ่งเป็น vision transcription noise ที่คาดไว้แล้ว (เหตุผลที่ให้ `vision_page` แยกจาก `text_page`
ตั้งแต่ Phase 1 — ความน่าเชื่อถือของ quote ไม่เท่ากัน)

**ตัดสินใจเลื่อนไม่ทำเอง**: `confidence` ของ `vision_page` ควรสื่อความเสี่ยงเรื่องอ่านภาพไม่ชัด
(เลอะ/เขียนมือ) ด้วยหรือไม่ — เป็นการขยายความหมายของกฎข้อ 4 ทั้งโปรเจกต์ ไม่ใช่แค่โค้ด รอผู้ใช้
ตัดสินใจก่อน ไม่ได้เปลี่ยนพฤติกรรม prompt ไปเองเงียบ ๆ

### สถานะรวม multi-format ingestion (2026-09-03)

**ครบทั้ง 5 phase ตามแผน** Phase 1-4 commit แล้ว (`c73c66f`) Phase 5 (vision OCR) เสร็จโค้ด +
test (120 ผ่านทั้งหมด) + live-verify แล้ว **ยังไม่ได้ commit** ตอนเขียนบรรทัดนี้

**ยืนยันจริงแล้ว**: PDF ข้อความปกติ (เดิม), PDF สแกนล้วนผ่าน vision (Anthropic, เอกสารจริง 16
หน้า), DOCX ที่มีแต่ paragraph (เอกสารจริงของผู้ใช้) **ยังไม่เคยยืนยันจริง**: XLSX (ปิดไว้ตาม
คำขอผู้ใช้), DOCX ที่มีค่ามาจาก table cell (ไม่มีเอกสารทดสอบที่มีข้อมูลในตาราง), vision บน
OpenAI/Gemini (โค้ดเขียนตาม SDK doc แต่ไม่เคยยิงจริง — ต่างจาก Anthropic ที่ยืนยันแล้ว)

**ค่าใช้จ่ายจริงในเซสชันนี้**: Phase 1 ~$0.07, Phase 4 ~$0.13, Phase 5 (3 รอบ เพราะเจอบั๊ก 2 ตัว
กลางทาง แต่ 2 รอบแรก fail ก่อนถึงขั้นเรียกโมเดลจริง — ไม่เสียเงินซ้ำ) ~$0.26 — รวมทั้งเซสชัน
ต่ำกว่า $0.50 ถามผู้ใช้ก่อนทุกจุดที่จะเสียเงินจริง

# TOR Analyzer — สถานะงาน (ต่อจากตรงนี้ได้)

ไฟล์นี้มีไว้ให้ Claude (หรือใครก็ตาม) เปิดงานต่อได้ทันทีถ้าเซสชันขาดหรือเครื่องปิดกะทันหัน
อ่านไฟล์นี้ก่อน แล้วดูแผนเต็มที่ `~/.claude/plans/for-this-project-i-elegant-spring.md`
(มีเหตุผล/หลักฐานเบื้องหลังการตัดสินใจทุกอย่างละเอียดกว่านี้มาก)

**อัปเดตล่าสุด:** 2026-09-02

---

## สถานะ repo

- **มี commit จริงแล้ว** (ผ่าน `/quick-commit` เท่านั้น ไม่เคย commit ตรงเองเลย):
  `f716f69` Initial commit -> `5bb5fff` Update README.md -> `cdd4358` Add TOR Analyzer app
  (backend, frontend, docker config) — commit ล่าสุดคือตอน Step 1-6 (v0.1 หลัก) เสร็จ
  งาน multi-provider migration (ดูหัวข้อด้านล่าง) **ยังไม่ได้ commit** ตอนเขียนบรรทัดนี้
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

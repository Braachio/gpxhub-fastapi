from fastapi import APIRouter, UploadFile, File, Form
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import io
import re
from typing import List, Dict, Any, Optional

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

try:
    import pdfplumber  # type: ignore
except Exception as e:  # pragma: no cover
    pdfplumber = None


router = APIRouter(prefix="/iracing/schedule", tags=["iracing-schedule"])


def _clean_text(text: str) -> str:
    # 온도/조건 정보 제거
    text = re.sub(r'\s*\d+°[FC](?:/\d+°[FC])?', '', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*Rain chance\s+\w+', '', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*Rolling\s+\d+\s*laps', '', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*Cautions\s+\w+', '', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*Qual scrutiny\s*-\s*\w+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\([^)]*\)', '', text)  # 괄호 내용 제거
    return re.sub(r"\s+", " ", text).strip()


def _parse_page_text(page_text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    
    print(f"DEBUG: Starting to parse page text (length: {len(page_text)})")
    print(f"DEBUG: First 1000 chars: {page_text[:1000]}")
    print(f"DEBUG: Looking for patterns in full text...")
    
    # 전체 텍스트에서 직접 패턴 매칭
    lines = page_text.split('\n')
    
    # 1. "R Class Series (OVAL)" 패턴 찾기
    class_series_patterns = [
        r"([A-Z])\s*Class\s*Series\s*\(([^)]+)\)",
        r"([A-Z])\s*Class\s*\(([^)]+)\)",
        r"Class\s*([A-Z])\s*Series\s*\(([^)]+)\)"
    ]
    
    current_class = None
    current_category = None
    
    for pattern in class_series_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 2:
                current_class = f"{match.group(1)} Class"
                current_category = _clean_text(match.group(2))
                print(f"DEBUG: Found class/category with pattern '{pattern}': {current_class} / {current_category}")
                break
    
    if not current_class:
        print("DEBUG: No class/category pattern found, trying standalone patterns...")
        # 단독 카테고리 패턴들도 시도
        standalone_patterns = [
            r"^OVAL\s*$", r"^SPORTS CAR\s*$", r"^FORMULA CAR\s*$", 
            r"^ROAD\s*$", r"^DIRT OVAL\s*$", r"^DIRT ROAD\s*$"
        ]
        
        for pattern in standalone_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE | re.MULTILINE)
            if match:
                current_category = match.group(0).strip()
                print(f"DEBUG: Found standalone category: {current_category}")
                break
    
    # 2. 시리즈명 찾기 (여러 패턴 시도)
    series_patterns = [
        r"([^-]+(?: - [^-]+)*?)\s*-?\s*2025\s*Season\s*\d+",
        r"([^-]+(?: - [^-]+)*?)\s*Series\s*by\s*[^-]+",
        r"(Mini Stock\s+[^-]+)",
        r"([^-]*Stock[^-]*)",
        r"([^-]*Series[^-]*)"
    ]
    
    current_series = None
    
    for pattern in series_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            current_series = _clean_text(match.group(1))
            print(f"DEBUG: Found series with pattern '{pattern}': {current_series}")
            break
    
    if current_series:
        # 클래스가 없으면 시리즈에서 추출
        if not current_class:
            car_type_match = re.search(r"(Mini Stock|GT3|GT4|Formula|LMP1|LMP2|GTE|Prototype|Touring|Truck)", current_series, re.IGNORECASE)
            if car_type_match:
                current_class = _clean_text(car_type_match.group(1))
                print(f"DEBUG: Extracted class from series: {current_class}")
    else:
        print("DEBUG: No series pattern found")
    
    # 3. 주차별 데이터 추출
    week_pattern = re.compile(r"Week\s+(\d+)\s*\((\d{4}-\d{2}-\d{2})[^)]*\)", re.IGNORECASE)
    week_matches = list(week_pattern.finditer(page_text))
    
    print(f"DEBUG: Found {len(week_matches)} week entries")
    
    for match in week_matches:
        week_idx = int(match.group(1))
        week_date = match.group(2)
        
        # 해당 주차 다음에 오는 트랙 정보 찾기
        start_pos = match.end()
        next_week_match = week_pattern.search(page_text, start_pos)
        end_pos = next_week_match.start() if next_week_match else len(page_text)
        
        track_section = page_text[start_pos:end_pos]
        print(f"DEBUG: Week {week_idx} track section: {track_section[:200]}")
        
        # 트랙명 추출 (첫 번째 라인에서)
        track_lines = track_section.split('\n')
        track_info = ""
        
        for track_line in track_lines:
            track_line = track_line.strip()
            if track_line and not re.search(r"Week\s+\d+", track_line, re.IGNORECASE):
                track_info = _clean_text(track_line)
                if track_info:
                    break
        
        if track_info:
            print(f"DEBUG: Week {week_idx} track: {track_info}")
            rows.append({
                "week": week_idx,
                "date": week_date,
                "track": track_info,
                "category": current_category or "Unknown",
                "series": current_series or "Unknown",
                "class": current_class or "Unknown"
            })
    
    print(f"DEBUG: Parsed {len(rows)} rows")
    return rows


async def _read_pdf_from_url(url: str) -> bytes:
    if httpx is None:
        raise HTTPException(status_code=500, detail="httpx 미설치")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"PDF 요청 실패: {r.status_code}")
        return r.content


def _parse_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    if pdfplumber is None:
        raise HTTPException(status_code=500, detail="pdfplumber 미설치")

    pages_processed = 0
    rows: List[Dict[str, Any]] = []
    series_name: Optional[str] = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages_processed += 1
            text = page.extract_text() or ""
            if pages_processed == 1:
                # 첫 페이지 상단의 시리즈명 라인 추정 (첫 줄)
                first_lines = (text.splitlines() or [""])[:3]
                if first_lines:
                    series_name = _clean_text(first_lines[0])
            rows.extend(_parse_page_text(text))

    return {
        "series": series_name or "",
        "pages": pages_processed,
        "count": len(rows),
        "rows": rows,
    }


@router.post("/parse")
async def parse_schedule(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
):
    try:
        if not file and not url:
            raise HTTPException(status_code=400, detail="파일 또는 url 중 하나가 필요합니다")

        pdf_bytes: bytes
        if url:
            pdf_bytes = await _read_pdf_from_url(url)
        else:
            assert file is not None
            pdf_bytes = await file.read()

        parsed = _parse_pdf_bytes(pdf_bytes)

        return JSONResponse(parsed)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파싱 실패: {e}")



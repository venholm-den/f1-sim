"""Conservative FIA PDF extraction into separate reviewable datasets."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests


def normalise(value):
    cleaned = re.sub(r'[^A-Z0-9 ]', '', unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().upper())
    return ' '.join(cleaned.split())


def published_utc(value):
    text = str(value).strip()
    match = re.fullmatch(r'(\d{2}\.\d{2}\.\d{2,4}) (\d{2}:\d{2}) (CET|CEST|UTC)', text)
    if match:
        date, time, zone = match.groups()
        year_format = '%y' if len(date.split('.')[-1]) == 2 else '%Y'
        local = pd.Timestamp(datetime.strptime(f'{date} {time}', f'%d.%m.{year_format} %H:%M'))
        return (local - pd.Timedelta(hours={'CET': 1, 'CEST': 2, 'UTC': 0}[zone])).tz_localize('UTC')
    try:
        stamp = pd.Timestamp(text)
        return stamp.tz_convert('UTC') if stamp.tzinfo is not None else pd.NaT
    except (ValueError, TypeError):
        return pd.NaT


def identify(name, roster):
    name = normalise(str(name).replace('*',''))
    matches = []
    for _, driver in roster.iterrows():
        broadcast = normalise(driver.get('BroadcastName', ''))
        surname = broadcast.split(' ', 1)[-1].strip()
        fullname = normalise(driver.get('FullName', ''))
        if (fullname and fullname == name) or (surname and (name == surname or name.endswith(' ' + surname))):
            matches.append(driver)
    if len(matches) != 1:
        return None
    return matches[0]


def grid_penalty_records(document, row, roster):
    """Extract sanctions from explicit decision fields or official grid footnotes.

    Narrative reasoning, summons, time penalties and penalty points are not grid
    penalties. Documents are associated only with their own event; carry-over to
    a later event is not guessed. A final grid remains authoritative for placement.
    """
    text = '\n'.join(page['text'] for page in document['pages'])
    title = str(row['document_title'])
    stamp = published_utc(row.get('published_at',''))
    base = {'Year':int(row['year']),'Event':row['event'],'Round':int(roster.Round.iloc[0]),
            'SourceURL':row['document_url'],'DocumentNumber':row.get('doc_number',''),
            'PublishedAtUtc':stamp.isoformat() if pd.notna(stamp) else '',
            'PublishedAtRaw':row.get('published_at',''),'Title':title,'Verified':True}
    records = []

    def record(number, decision, evidence, reason=''):
        matched = roster[pd.to_numeric(roster.DriverNumber,errors='coerce').eq(int(number))]
        if len(matched) != 1:
            raise ValueError(f'Unmapped or ambiguous car {number} in penalty evidence.')
        driver = matched.iloc[0]
        clean = ' '.join(decision.split())
        if re.search(r'\bno\s+(?:(?:further|additional)\s+)?penalt(?:y|ies)\b|\bno\s+further\s+action\b',clean,re.I):
            kind,places = 'no_penalty',None
        elif re.search(r'(?:start|starting).*?pit\s*lane',clean,re.I):
            kind,places = 'pit_lane',None
        elif re.search(r'(?:back|rear)\s+of\s+(?:the\s+)?(?:starting\s+)?grid',clean,re.I):
            kind,places = 'back_of_grid',None
        else:
            found = re.search(r'(\d+)\s*(?:[-–]\s*)?(?:place(?:s)?\s+(?:starting\s+)?grid\s+penalt(?:y|ies)|grid\s+(?:positions?|places?))',clean,re.I)
            if not found:
                return
            kind,places = 'grid_drop',int(found.group(1))
        # A penalty imposed after a Sprint can apply to the Grand Prix. Its
        # target comes from the decision itself, not the incident's Session field.
        target = 'S' if re.search(r'\b(?:the|next|for the)\s+sprint\b',clean,re.I) else 'R'
        explicit_race = bool(re.search(r'\b(?:next\s+race|the\s+race|grand\s+prix|starting grid)\b',clean,re.I))
        if kind != 'no_penalty' and 'starting grid' not in title.lower() and target == 'R' and not explicit_race:
            # A bare numeric "grid penalty" in a decision with no target is
            # useful evidence, but cannot silently become a Sunday penalty.
            target = ''
        refs = re.findall(r"document\s+(?:no\.?|number)\s*(\d+)",reason,re.I)
        number_id = str(row.get('doc_number','')).replace('Doc ','')
        records.append({**base,'Driver':driver.Abbreviation,'Team':driver.TeamName,
            'CarNumber':int(number),'TargetSession':target,'PenaltyType':kind,'GridPlaces':places,
            'DecisionText':clean,'Reason':reason,'EvidenceType':evidence,
            'DecisionReference':refs[0] if len(refs)==1 else number_id,
            'PlacementPolicy':'official_grid_only; numeric drops are not added independently'})

    if 'starting grid' in title.lower():
        target = row.get('session','')
        for line in text.splitlines():
            match = re.match(r'^\s*Cars?\s+(\d+(?:\s*(?:&|and|,)\s*\d+)*)\s*[-–]\s*(.+)',line,re.I)
            if match and re.search(r'grid\s+penalt|pit\s*lane|back\s+of.*?grid',match.group(2),re.I):
                for number in re.findall(r'\d+',match.group(1)):
                    record(number,match.group(2),'explicit_official_grid_footnote',match.group(2))
                    if records:
                        records[-1]['TargetSession'] = target
        return records
    if 'summons' in title.lower():
        return []
    decision = re.search(r'^\s*Decision\s*:?\s*(.+?)(?=^\s*Reasons?\b|\Z)',text,re.I|re.M|re.S)
    if not decision:
        return []
    driver = re.search(r'No\s*/\s*Driver\s*:?\s*(\d+)\s*[-–]',text,re.I)
    number = driver.group(1) if driver else None
    title_number = re.search(r'\bCar\s+(\d+)\b',title,re.I)
    if not number or (title_number and title_number.group(1) != number):
        raise ValueError('Decision car identity is missing or contradicts the title.')
    record(number,decision.group(1),'explicit_stewards_decision')
    return records


def parse_document(document, row, roster):
    """Full grids only; entry lists stop before reserve/FP1 drivers.

    Explicit decisions and grid footnotes are evidence, never arithmetic grid
    adjustments. Unmapped/new drivers quarantine the whole list.
    """
    title = str(row['document_title']).lower()
    text = '\n'.join(page['text'] for page in document['pages'])
    stamp = published_utc(row['published_at'])
    base = {'Year': int(row['year']), 'Event': row['event'], 'SourceURL': row['document_url'],
            'Round': int(roster.Round.iloc[0]), 'Session': row.get('session', ''),
            'RosterSize': len(roster),
            'PublishedAtUtc': stamp.isoformat() if pd.notna(stamp) else '',
            'PublishedAtRaw': row['published_at'],
            'PublicationTimePolicy': 'literal_source_timezone; undated excluded from as-of selection'}
    if 'starting grid' in title:
        if row.get('session') != 'R' or 'sprint' in title:
            raise ValueError('Sprint/qualifying grids cannot be used as a Grand Prix grid.')
        found = []
        for page in document['pages']:
            # Full text recovers lines at column boundaries; column text avoids
            # merged team/driver lines in the staggered starting-grid layout.
            for column in [page['text'],*page.get('columns',[])]:
                for line in column.splitlines():
                    match = re.match(r'^\s*(\d{1,2})\s+(\d{1,3})\s+(.+?)(?:\s+\d:\d{2}\.\d{3})?\s*$', line)
                    if not match:
                        continue
                    position, number, name = match.groups()
                    driver = identify(name, roster)
                    if driver is None or str(int(float(driver.DriverNumber))) != str(int(number)):
                        continue
                    found.append({**base, 'Driver': driver.Abbreviation, 'Team': driver.TeamName,
                                  'GridPosition': int(position), 'PitLaneStart': False, 'DocumentType': title,
                                  'EntryListId': hashlib.sha256(row['document_url'].encode()).hexdigest()[:16]})
        # Only explicitly labelled pit-lane entrants are accepted; never infer
        # a pit-lane start from a missing grid row or a narrative penalty.
        pit_lane = False
        for line in text.splitlines():
            if re.fullmatch(r'\s*(?:DRIVERS REQUIRED TO START FROM THE\s+)?PIT\s+LANE\s*', line, re.I):
                pit_lane = True
                continue
            if pit_lane and re.search(r'^\s*\*?\s*(?:PENALTIES|NOTES)\b',line,re.I):
                pit_lane = False
            if not pit_lane:
                continue
            match = re.match(r'^\s*(\d{1,3})\s+(.+?)(?:\s+\d:\d{2}\.\d{3})?\s*$', line)
            if match:
                driver = identify(match.group(2), roster)
                if driver is not None and str(int(float(driver.DriverNumber))) == str(int(match.group(1))):
                    found.append({**base, 'Driver': driver.Abbreviation, 'Team': driver.TeamName,
                                  'GridPosition': 0, 'PitLaneStart': True, 'DocumentType': title,
                                  'EntryListId': hashlib.sha256(row['document_url'].encode()).hexdigest()[:16]})
        # A withdrawn entrant is not an unparsed pit-lane starter. Keep the
        # explicit status so complete roster coverage remains verifiable.
        for number in re.findall(r'^\s*Car\s+(\d+)\s*[-–]\s*Withdrawn\b',text,re.I|re.M):
            matched = roster[pd.to_numeric(roster.DriverNumber,errors='coerce').eq(int(number))]
            if len(matched)==1:
                driver = matched.iloc[0]
                found.append({**base,'Driver':driver.Abbreviation,'Team':driver.TeamName,
                    'GridPosition':-1,'PitLaneStart':False,'Withdrawn':True,'DocumentType':title,
                    'EntryListId':hashlib.sha256(row['document_url'].encode()).hexdigest()[:16]})
        frame = pd.DataFrame(found).drop_duplicates() if found else pd.DataFrame()
        if not frame.empty:
            frame['Withdrawn'] = frame.get('Withdrawn',pd.Series(False,index=frame.index)).astype(str).str.lower().eq('true')
        positive = frame[frame.GridPosition.gt(0)] if not frame.empty else frame
        if frame.empty or len(frame) != len(roster) or frame.Driver.duplicated().any() or positive.GridPosition.duplicated().any() or not positive.GridPosition.between(1, len(roster)).all():
            raise ValueError('Incomplete or unsupported grid layout/pit-lane entries; review PDF.')
        return 'grids', frame.to_dict('records')
    if 'entry list' in title:
        found = []
        text = '\n'.join(page.get('entry_text',page['text']) for page in document['pages'])
        for line in text.splitlines():
            if re.search(r'in addition|following drivers|take part in P1', line, re.I):
                break
            match = re.match(r'^\s*(\d{1,4})\s+(?:[A-Z]{3}\s+)?(.+?)\s+([A-Z]{3})\s+(.+)$', line)
            if not match:
                continue
            number, name, nationality, team = match.groups()
            driver = identify(name, roster)
            if driver is None or int(float(driver.DriverNumber)) != int(number):
                raise ValueError('Unmapped entry-list driver; no fabricated abbreviation.')
            found.append({**base, 'Driver': driver.Abbreviation, 'Team': driver.TeamName,
                          'OfficialTeamText': team, 'EntryListId': hashlib.sha256(row['document_url'].encode()).hexdigest()[:16]})
        if len(found) != len(roster) or len({r['Driver'] for r in found}) != len(found):
            raise ValueError('Incomplete or unsupported entry list; reserve drivers excluded.')
        return 'entries', found
    if 'infringement' in title or 'decision' in title or 'penalty' in title:
        penalties = grid_penalty_records(document,row,roster)
        if penalties:
            return 'grid_penalties',penalties
        return 'penalty_evidence', [{**base, 'Title': row['document_title'], 'EvidenceText': text,
                                     'Verified': False, 'Status': 'review_required'}]
    return 'other_evidence', [{**base, 'Title': row['document_title'], 'EvidenceText': text,
                               'Verified': False, 'Status': 'review_required'}]


def collect(index, results, output, pdf_python, max_documents=100, get=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cache = output/'sources'
    cache.mkdir()
    tables, log = {}, []
    helper = Path(__file__).resolve().parents[2]/'scripts/extract_fia_pdf_text.py'
    relevant = index[index.document_title.str.contains('starting grid|entry list|infringement|penalty|power unit|tyre', case=False, na=False)]
    relevant = relevant[~(relevant.document_title.str.contains('starting grid', case=False) &
                          (relevant.session.ne('R') | relevant.document_title.str.contains('sprint', case=False)))]
    # Prioritise full lists/grids before narrative evidence within the request bound.
    relevant = relevant.assign(_priority=~relevant.document_title.str.contains('starting grid|entry list', case=False)).sort_values(['_priority', 'year', 'event', 'published_at'], ascending=[True, False, True, True])
    attempted = 0
    for row in relevant.to_dict('records'):
        roster = results[results.Year.eq(int(row['year'])) & results.Event.eq(row['event']) & results.Session.eq('Q')]
        roster = roster.drop_duplicates('Abbreviation')
        if roster.empty:
            continue
        if attempted >= max_documents:
            break
        attempted += 1
        record = {'url': row['document_url'], 'title': row['document_title'], 'year': int(row['year']), 'event': row['event'],
                  'published_at_raw': row['published_at'], 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            parsed = urlparse(row['document_url'])
            if parsed.scheme != 'https' or parsed.hostname not in {'www.fia.com', 'fia.com'}:
                raise ValueError('Only official HTTPS FIA PDFs are supported.')
            response = (get or requests.get)(row['document_url'], timeout=25)
            response.raise_for_status()
            if not response.content.startswith(b'%PDF') or len(response.content) > 20_000_000:
                raise ValueError('Expected a PDF under 20 MB.')
            digest = hashlib.sha256(response.content).hexdigest()
            record['sha256'] = digest
            file = cache/f'{digest}.pdf'
            if not file.exists():
                file.write_bytes(response.content)
            extracted = subprocess.run([str(pdf_python), str(helper), str(file)], capture_output=True, text=True, check=True, timeout=45)
            document = json.loads(extracted.stdout)
            (cache/f'{digest}.json').write_text(json.dumps(document, indent=2), encoding='utf-8')
            kind, rows = parse_document(document, row, roster)
            tables.setdefault(kind, []).extend({**r, 'PdfSHA256': digest} for r in rows)
            if kind == 'grids':
                tables.setdefault('grid_penalties', []).extend(
                    {**r, 'PdfSHA256': digest} for r in grid_penalty_records(document,row,roster))
            record.update(status='extracted', table=kind, rows=len(rows), sha256=digest)
        except (requests.RequestException, ValueError, OSError, subprocess.SubprocessError, KeyError) as exc:
            record.update(status='unavailable_or_review_required', error=str(exc)[:240])
        log.append(record)
        print(f"FIA {attempted}: {row['year']} {row['event']} {row['document_title']} — {record['status']}", flush=True)
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(output/f'{name}.csv', index=False)
    report = {'attempted': attempted, 'extracted': sum(r['status'] == 'extracted' for r in log),
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'documents': log,
              'activated': False, 'index_updated': False, 'tables': {k: len(v) for k, v in tables.items()}}
    (output/'collection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def reparse_cached(collection_dir, index, results, output):
    """Re-evaluate captured PDFs without downloading or changing earlier outputs."""
    collection_dir, output = Path(collection_dir), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    original = json.loads((collection_dir/'collection.json').read_text(encoding='utf-8'))
    tables, records = {}, []
    for item in original['documents']:
        digest = item.get('sha256')
        captured = Path(item.get('text_path') or collection_dir/'sources'/f'{digest}.json')
        pdf = Path(item.get('pdf_path') or collection_dir/'sources'/f'{digest}.pdf')
        if not digest or not captured.exists() or not pdf.exists():
            continue
        row = index[index.document_url.eq(item['url'])].iloc[0].to_dict()
        roster = results[results.Year.eq(int(row['year'])) & results.Event.eq(row['event']) & results.Session.eq('Q')].drop_duplicates('Abbreviation')
        record = {**item, 'pdf_path': str(pdf.resolve()), 'text_path': str(captured.resolve())}
        try:
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != digest:
                raise ValueError('Captured PDF checksum failed.')
            document = json.loads(captured.read_text(encoding='utf-8'))
            kind, rows = parse_document(document, row, roster)
            tables.setdefault(kind, []).extend({**r, 'PdfSHA256': digest} for r in rows)
            if kind == 'grids':
                tables.setdefault('grid_penalties', []).extend(
                    {**r, 'PdfSHA256': digest} for r in grid_penalty_records(document,row,roster))
            record.update(status='extracted', table=kind, rows=len(rows))
            record.pop('error', None)
        except ValueError as exc:
            record.update(status='unavailable_or_review_required', error=str(exc))
        records.append(record)
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(output/f'{name}.csv', index=False)
    report = {'attempted': len(records), 'extracted': sum(r['status'] == 'extracted' for r in records),
              'documents': records, 'tables': {k: len(v) for k, v in tables.items()}, 'activated': False,
              'source_collection': str(collection_dir.resolve()), 'index_updated': False}
    (output/'collection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def asof_grid(grids, year, event, cutoff):
    """Pick one complete publication version. Never combine revised grids."""
    stamp = pd.Timestamp(cutoff)
    if stamp.tzinfo is None:
        raise ValueError('Grid cutoff must be timezone-aware.')
    frame = grids[grids.Year.eq(year) & grids.Event.eq(event)].copy()
    frame['_published'] = pd.to_datetime(frame.PublishedAtUtc, utc=True, errors='coerce')
    frame = frame[frame._published.le(stamp)]
    if frame.empty:
        return frame.drop(columns='_published')
    latest = frame._published.max()
    candidates = frame[frame._published.eq(latest)]
    # Equal timestamps from distinct versions need a human decision.
    if candidates.EntryListId.nunique() != 1:
        raise ValueError('Ambiguous grid versions at the same publication time.')
    positive = candidates[candidates.GridPosition.gt(0)]
    withdrawn = candidates.get('Withdrawn',pd.Series(False,index=candidates.index)).fillna(False).astype(str).str.lower().eq('true')
    invalid = ~(candidates.GridPosition.gt(0) | (candidates.GridPosition.eq(0)&candidates.PitLaneStart.astype(str).str.lower().eq('true')) | (candidates.GridPosition.eq(-1)&withdrawn))
    if 'RosterSize' not in candidates or not candidates.RosterSize.eq(len(candidates)).all() or candidates.Driver.duplicated().any() or positive.GridPosition.duplicated().any() or not positive.GridPosition.between(1, len(candidates)).all() or invalid.any():
        raise ValueError('Grid version is incomplete or has duplicate rows.')
    return candidates.drop(columns='_published')

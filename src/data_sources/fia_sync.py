"""Bounded, resumable FIA indexing and PDF enrichment for the PC scheduler."""
from __future__ import annotations

from src.data_sources.fastf1_cache import enable_cache

from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pandas as pd
import requests

from src.data_sources.fia_documents import (FIA_DOCUMENT_COLUMNS,fia_f1_documents_url,
    parse_fia_document_listing_html,parse_fia_event_urls,merge_fia_document_rows)
from src.data_sources.fia_extraction import parse_document,grid_penalty_records,published_utc

EXTRACTION_VERSION = 'fia_v2'


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return {}


def atomic_json(path,data):
    path = Path(path)
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temporary,path)


def cached_roster(root,year,event):
    """Same-event identities only. No future race result is requested."""
    import fastf1
    cache = Path(root)/'data/cache'
    if not cache.is_dir():
        return pd.DataFrame()
    enable_cache(str(cache))
    # Restore the caller's offline setting even if a session cannot be loaded.
    previous = fastf1.Cache._requests_session_cached.settings.only_if_cached
    try:
        fastf1.Cache.offline_mode(True)
        for code in ('Q','SQ','FP3','FP2','FP1'):
            try:
                session = fastf1.get_session(year,event,code)
                session.load(laps=False,telemetry=False,weather=False,messages=False)
                frame = session.results.copy()
                required = {'Abbreviation','DriverNumber','TeamName','BroadcastName'}
                if not frame.empty and required.issubset(frame):
                    frame = frame.dropna(subset=['Abbreviation','DriverNumber']).copy()
                    if frame.Abbreviation.duplicated().any() or frame.DriverNumber.duplicated().any():
                        continue
                    frame['Round'] = int(session.event.RoundNumber)
                    return frame
            except Exception:
                continue
    finally:
        fastf1.Cache.offline_mode(previous)
    return pd.DataFrame()


def extract_pdf(path,pdf_python=None):
    if importlib.util.find_spec('pdfplumber'):
        from scripts.extract_fia_pdf_text import extract
        return extract(path)
    if importlib.util.find_spec('pypdf'):
        from pypdf import PdfReader
        return {'pages':[{'text':page.extract_text() or '', 'columns':[]} for page in PdfReader(path).pages]}
    if pdf_python and Path(pdf_python).is_file():
        helper = Path(__file__).resolve().parents[2]/'scripts/extract_fia_pdf_text.py'
        result = subprocess.run([str(pdf_python),str(helper),str(path)],capture_output=True,
                                text=True,check=True,timeout=45)
        return json.loads(result.stdout)
    raise RuntimeError('PDF parser unavailable; configure pdf_python with an existing PDF-capable Python.')


def derived_rows(document,row,roster,pdf_sha,seen):
    kind, records = parse_document(document,row,roster)
    output = []
    if kind in {'grids','entries'}:
        for record in records:
            item = {**row,'driver':record['Driver'],'team':record['Team'],
                'status':'verified_grid' if kind=='grids' else 'verified_entry',
                'grid_position':record.get('GridPosition',''),'roster_size':len(roster),
                'pit_lane_start':record.get('PitLaneStart',False),'withdrawn':record.get('Withdrawn',False)}
            output.append(item)
    sanctions = records if kind=='grid_penalties' else grid_penalty_records(document,row,roster)
    for record in sanctions:
        output.append({**row,'driver':record['Driver'],'team':record['Team'],
            'document_type':'grid_penalty' if kind=='grids' else row['document_type'],
            'penalty_type':record['PenaltyType'],'penalty_value':record['GridPlaces'],
            'target_session':record['TargetSession'],'decision_text':record['DecisionText'],
            'decision_reference':record['DecisionReference'],'status':'verified_decision',
            'notes':record['EvidenceType']+'; '+record['PlacementPolicy']})
    for item in output:
        item.update(pdf_sha256=pdf_sha,first_seen_at_utc=seen,extraction_version=EXTRACTION_VERSION)
    return output,kind


def refresh(root,*,year=None,force=False,all_events=False,pdf_python=None,
            max_documents=24,now=None,get=None,roster_loader=None,extractor=None):
    """Caller owns the workspace lock. Failed refreshes preserve the prior CSV."""
    root = Path(root).resolve()
    config = read_json(root/'config/fia_sync.json')
    parser_sha = digest(b''.join(path.read_bytes() for path in (
        Path(__file__).with_name('fia_extraction.py'),
        Path(__file__).resolve().parents[2]/'scripts/extract_fia_pdf_text.py')))
    if not force and not config.get('enabled',False):
        return {'status':'disabled'}
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        raise ValueError('FIA retrieval time must be timezone aware.')
    year = int(year or current.year)
    directory = root/'data/fia_documents'
    directory.mkdir(parents=True,exist_ok=True)
    state_path = directory/'sync_state.json'
    state = read_json(state_path)
    last = pd.to_datetime(state.get('last_attempt_at_utc'),utc=True,errors='coerce')
    interval = int(config.get('refresh_seconds',3600)) if state.get('last_status')=='completed' else 600
    if not force and pd.notna(last) and (current-last).total_seconds()<interval:
        return {'status':'not_due','last_status':state.get('last_status'),'last_report':state.get('last_report')}
    folder = directory/'captures'/current.strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    index_path = directory/'fia_document_index.csv'
    old = index_path.read_bytes() if index_path.is_file() else None
    if old is not None:
        (folder/'index_before.csv').write_bytes(old)
    existing = pd.read_csv(index_path).fillna('') if old else pd.DataFrame(columns=FIA_DOCUMENT_COLUMNS)
    client = get or requests.get
    documents, failures, listings = [], [], []
    cached_skipped = 0
    try:
        url = fia_f1_documents_url(year)
        response = client(url,timeout=20);response.raise_for_status()
        if '<html' not in response.text.lower():
            raise ValueError('FIA listing did not return HTML.')
        (folder/'listing.html').write_text(response.text,encoding='utf-8')
        listings = parse_fia_document_listing_html(response.text,year,url)
        if all_events:
            for i,event_url in enumerate(parse_fia_event_urls(response.text,url)):
                page = client(event_url,timeout=20);page.raise_for_status()
                (folder/f'event_{i}.html').write_text(page.text,encoding='utf-8')
                listings.extend(parse_fia_document_listing_html(page.text,year,event_url))
        if not listings:
            raise ValueError('No FIA document listings found; previous index retained.')
        unique = {(l.year,l.event,l.doc_number,l.document_url):l for l in listings}
        listings = list(unique.values())
        metadata = []
        for listing in listings:
            row = listing.to_row()
            prior = existing[existing.year.eq(year)&existing.event.eq(listing.event)&
                             existing.document_url.eq(listing.document_url)&existing.doc_number.eq(listing.doc_number)]
            known = pd.to_datetime(prior.get('first_seen_at_utc',pd.Series(dtype=str)),utc=True,errors='coerce').dropna()
            row['first_seen_at_utc'] = known.min().isoformat() if not known.empty else current.isoformat()
            metadata.append(row)
        relevant = [row for row in metadata if row['status']!='recalled' and
            (('starting grid' in row['document_title'].lower() and row['session']=='R') or
             'entry list' in row['document_title'].lower() or
             (row['document_type'] in {'infringement','stewards decision'} and 'Car ' in row['document_title']))]
        relevant.sort(key=lambda r:('starting grid' not in r['document_title'].lower(),
                                    -int(r['doc_number'].replace('Doc ','') or 0) if r['doc_number'].replace('Doc ','').isdigit() else 0))
        rows = list(metadata)
        rosters = {}
        cache = directory/'cache'
        cache.mkdir(exist_ok=True)
        started = time.monotonic()
        for row in relevant:
            if len(documents)>=max_documents or time.monotonic()-started>100:
                break
            key = row['document_url']
            previous = state.get('documents',{}).get(key,{})
            checked = pd.to_datetime(previous.get('checked_at_utc'),utc=True,errors='coerce')
            if (not force and previous.get('parser_version')==EXTRACTION_VERSION
                    and previous.get('parser_sha256')==parser_sha
                    and previous.get('published_at')==row['published_at']
                    and previous.get('status')=='extracted' and pd.notna(checked)
                    and (current-checked).total_seconds()<21600 and 'starting grid' not in row['document_title'].lower()):
                cached_skipped += 1
                continue
            record = {'url':key,'title':row['document_title'],'event':row['event'],
                'published_at':row['published_at'],'checked_at_utc':current.isoformat(),
                'parser_version':EXTRACTION_VERSION}
            record['parser_sha256'] = parser_sha
            try:
                if row['event'] not in rosters:
                    rosters[row['event']] = (roster_loader or cached_roster)(root,year,row['event'])
                roster = rosters[row['event']]
                if roster.empty:
                    raise ValueError('Same-event cached driver identities unavailable; retained for retry.')
                from urllib.parse import urlparse
                parsed = urlparse(key)
                if parsed.scheme!='https' or parsed.hostname not in {'fia.com','www.fia.com'}:
                    raise ValueError('Only official HTTPS FIA PDF URLs are accepted.')
                pdf = client(key,timeout=20);pdf.raise_for_status()
                if not pdf.content.startswith(b'%PDF') or len(pdf.content)>20_000_000:
                    raise ValueError('Expected an official PDF under 20 MB.')
                sha = digest(pdf.content)
                record['pdf_sha256'] = sha
                path = cache/f'{sha}.pdf'
                if not path.exists():
                    path.write_bytes(pdf.content)
                document = (extractor or extract_pdf)(path,pdf_python or config.get('pdf_python'))
                extracted_text = json.dumps(document,indent=2)
                text_path = cache/f'{sha}.{EXTRACTION_VERSION}.{digest(extracted_text.encode())[:12]}.json'
                if not text_path.exists():
                    text_path.write_text(extracted_text,encoding='utf-8')
                # Seeing a listing does not prove the later PDF version was
                # available then. A newly parsed content hash starts now.
                prior_version = existing[existing.document_url.eq(key)]
                if 'pdf_sha256' in prior_version and 'extraction_version' in prior_version:
                    prior_version = prior_version[prior_version.pdf_sha256.eq(sha)&
                                                  prior_version.extraction_version.eq(EXTRACTION_VERSION)&
                                                  prior_version.status.isin(['verified_grid','verified_entry','verified_decision'])]
                else:
                    prior_version = prior_version.iloc[:0]
                observed = pd.to_datetime(prior_version.get('first_seen_at_utc',pd.Series(dtype=str)),
                                          utc=True,errors='coerce').dropna()
                seen = observed.min().isoformat() if not observed.empty else current.isoformat()
                derived,kind = derived_rows(document,row,roster,sha,seen)
                rows.extend(derived)
                record.update(status='extracted',rows=len(derived),kind=kind,pdf_sha256=sha,
                              pdf_path=str(path),text_path=str(text_path))
                if not derived and kind in {'penalty_evidence','other_evidence'}:
                    record.update(status='review_required',error='No supported explicit grid decision; raw evidence retained.')
                    failures.append(record)
            except Exception as exc:
                record.update(status='review_required',error_type=type(exc).__name__,error=str(exc)[:300])
                failures.append(record)
            known_sha = set(existing.loc[existing.document_url.eq(key),'pdf_sha256'].dropna()) if 'pdf_sha256' in existing else set()
            if (record['status']=='review_required' and 'starting grid' in row['document_title'].lower()
                    and record.get('pdf_sha256') and record['pdf_sha256'] not in known_sha):
                rows.append({**row,'status':'review_required','first_seen_at_utc':current.isoformat(),
                    'extraction_version':EXTRACTION_VERSION,'pdf_sha256':record.get('pdf_sha256',''),
                    'notes':record['error']})
            documents.append(record)
            print(f"FIA {record['title']}: {record['status']}",flush=True)
        merged = merge_fia_document_rows(existing,rows)
        snapshot = folder/'index_after.csv'
        merged.to_csv(snapshot,index=False)
        temporary = index_path.with_name('fia_document_index.'+uuid4().hex+'.tmp')
        temporary.write_bytes(snapshot.read_bytes())
        os.replace(temporary,index_path)
        report = {'status':'completed','year':year,'retrieved_at_utc':current.isoformat(),
            'listings':len(listings),'index_rows':len(merged),'index_sha256':digest(index_path.read_bytes()),
            'rows_added':len(merged)-len(existing),'documents':documents,'review_required':len(failures),
            'cached_documents':cached_skipped,
            'pending_documents':max(0,len(relevant)-len(documents)-cached_skipped),
            'index_backup':str(folder/'index_before.csv'),'applied_to_frozen_forecasts':False,
            'source_listing_url':url,'listing_sha256':digest(response.text.encode()),
            'parser_version':EXTRACTION_VERSION,'parser_sha256':parser_sha}
    except Exception as exc:
        report = {'status':'failed','error_type':type(exc).__name__,'error':str(exc)[:300],
                  'retrieved_at_utc':current.isoformat(),'previous_index_preserved':True}
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    updated = {**state,'last_attempt_at_utc':current.isoformat(),'last_status':report['status'],
               'last_report':str(folder/'report.json')}
    updated['documents'] = {**state.get('documents',{}),**{r['url']:r for r in documents}}
    atomic_json(state_path,updated)
    return {**report,'report_path':str(folder/'report.json')}

"""Merge PC FIA updates into the desktop's managed index, preserving backups."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

import pandas as pd

from src.data_sources.fia_documents import FIA_DOCUMENT_COLUMNS, merge_fia_document_rows
from src.data_sources.fia_extraction import published_utc

_lock = threading.Lock()
RELATIVE_INDEX = Path('data/fia_documents/fia_document_index.csv')


def sha(content):
    return hashlib.sha256(content).hexdigest()


# Several UI calls sync in one chain and the UI polls; skip rereading and
# rehashing both indexes when neither file has changed since the last sync.
_last_sync: dict = {}


def _stamp(path):
    try:
        info = path.stat()
        return info.st_mtime_ns, info.st_size, info.st_ino
    except OSError:
        return None


def _remember(source, target, result):
    _last_sync.clear()
    if result.get('status') in {'current', 'updated'}:
        _last_sync.update(key=(str(source), str(target), _stamp(source), _stamp(target)), result=result)
    return result


def sync_pc_index(workspace, pc_workspace, configured_path, *, following=True):
    """Only the default managed index follows PC runs; custom paths stay local."""
    workspace, pc_workspace = Path(workspace).resolve(), Path(pc_workspace).resolve()
    target = Path(configured_path).expanduser()
    target = (workspace/target).resolve() if not target.is_absolute() else target.resolve()
    if not following:
        return {'status':'disabled'}
    if target != (workspace/RELATIVE_INDEX).resolve():
        return {'status':'custom_source','path':str(target)}
    source = pc_workspace/RELATIVE_INDEX
    if source.resolve()==target:
        return {'status':'using_pc_index','path':str(target)}
    if not source.is_file():
        return {'status':'pc_index_unavailable','path':str(target),'source_path':str(source)}
    with _lock:
        if _last_sync.get('key') == (str(source), str(target), _stamp(source), _stamp(target)):
            return {**_last_sync['result'], 'status': 'current'}
        try:
            source_bytes = source.read_bytes()
            old = target.read_bytes() if target.is_file() else b''
            source_sha, local_sha = sha(source_bytes), sha(old)
            receipt_path = workspace/'outputs/fia_reference_sync.json'
            try:
                previous = json.loads(receipt_path.read_text(encoding='utf-8'))
                if not isinstance(previous,dict):
                    previous = {}
            except (OSError,ValueError):
                previous = {}
            if previous.get('source_sha256')==source_sha and previous.get('destination_sha256')==local_sha:
                return _remember(source, target, {**previous,'status':'current'})
            incoming = pd.read_csv(BytesIO(source_bytes)).fillna('')
            required = {'year','event','document_type','document_title','document_url','published_at'}
            if incoming.empty or not required.issubset(incoming):
                raise ValueError('PC FIA index is incomplete; local dataset retained.')
            existing = pd.read_csv(BytesIO(old)).fillna('') if old else pd.DataFrame(columns=FIA_DOCUMENT_COLUMNS)
            if set(existing)-set(FIA_DOCUMENT_COLUMNS):
                return {'status':'custom_columns','path':str(target),'message':'Custom columns retained; automatic merge skipped.'}
            merged = merge_fia_document_rows(existing,incoming.to_dict('records'))
            merged['_publication_utc'] = pd.to_datetime(merged.published_at.map(published_utc),utc=True,errors='coerce')
            merged = merged.sort_values('_publication_utc',ascending=False,na_position='last',kind='stable').drop(columns='_publication_utc')
            output = merged.to_csv(index=False).encode('utf-8')
            stamp = datetime.now(timezone.utc)
            # No-op syncs never rewrite the local index or its modification time.
            backup = ''
            if output!=old:
                target.parent.mkdir(parents=True,exist_ok=True)
                if old:
                    path = target.parent/'sync_backups'/f'{stamp.strftime("%Y%m%dT%H%M%S%fZ")}_{local_sha[:12]}.csv'
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(old)
                    backup = str(path)
                # Do not overwrite edits made while the merge was being built.
                if (target.read_bytes() if target.is_file() else b'')!=old:
                    return {'status':'local_changed','message':'Dataset changed during sync; retry later.'}
                temporary = target.with_name(target.name+'.'+uuid4().hex+'.tmp')
                temporary.write_bytes(output)
                os.replace(temporary,target)
            latest = merged.iloc[0] if not merged.empty else {}
            result = {'status':'updated' if output!=old else 'current','path':str(target),
                'source_path':str(source),'source_sha256':source_sha,'destination_sha256':sha(output),
                'row_count':len(merged),'latest_event':latest.get('event',''),
                'latest_published_at':latest.get('published_at',''),'synced_at_utc':stamp.isoformat(),
                'backup_path':backup,'frozen_forecasts_modified':False}
            receipt_path.parent.mkdir(parents=True,exist_ok=True)
            temporary = receipt_path.with_name(receipt_path.name+'.'+uuid4().hex+'.tmp')
            temporary.write_text(json.dumps(result,indent=2),encoding='utf-8')
            os.replace(temporary,receipt_path)
            return _remember(source, target, result)
        except (OSError,ValueError,KeyError,TypeError,pd.errors.ParserError) as exc:
            return {'status':'error','message':str(exc)[:250],'path':str(target),
                    'local_dataset_preserved':True}

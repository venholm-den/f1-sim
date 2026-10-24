from pathlib import Path

import pandas as pd

from src.app_services.fia_reference_sync import RELATIVE_INDEX, sync_pc_index
from src.app_services.workbench import data_preview


def write_index(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(path,index=False)


def row(event='Singapore Grand Prix',publication='10.10.26 21:01 CET',**changes):
    return {'year':2026,'event':event,'document_type':'document','document_title':'Latest decision',
            'doc_number':'Doc 1','document_url':'https://www.fia.com/decision.pdf',
            'published_at':publication,**changes}


def test_default_preview_sorts_all_dates_before_pagination_and_puts_undated_last(tmp_path):
    path=tmp_path/'fia.csv'
    rows=[row('Old',f'{day:02d}.09.26 12:00 CET',doc_number=f'Doc {day}') for day in range(1,14)]
    rows += [row('Undated',''), row('Latest','10.10.26 21:01 CET'),row('Last year','31.12.25 23:30 CET')]
    write_index(path,rows)
    config={'data':{'fia_document_index_path':str(path)}}
    first=data_preview(config,'fia_document_index',1)
    last=data_preview(config,'fia_document_index',2)
    assert first['rows'][0]['event']=='Latest'
    assert first['rows'][1]['published_at']=='13.09.26 12:00 CET'
    assert last['rows'][-1]['event']=='Undated'
    assert first['sort']=={'column':'published_at','direction':'desc'}
    assert len(first['rows'])==10 and len(last['rows'])==6


def test_preview_uses_timezone_offsets_not_raw_text_sorting(tmp_path):
    path=tmp_path/'fia.csv'
    write_index(path,[row('Earlier','10.10.26 21:00 CEST'),row('Later','2026-10-10T19:30:00Z')])
    result=data_preview({'data':{'fia_document_index_path':str(path)}},'fia_document_index')
    assert result['rows'][0]['event']=='Later'


def test_sync_merges_pc_updates_preserves_local_rows_and_backup_and_source(tmp_path):
    local,pc=tmp_path/'desktop',tmp_path/'pc'
    target,source=local/RELATIVE_INDEX,pc/RELATIVE_INDEX
    write_index(target,[row('Local extra','01.01.25 12:00 CET',document_url='https://www.fia.com/local.pdf')])
    write_index(source,[row()])
    before,source_before=target.read_bytes(),source.read_bytes()
    result=sync_pc_index(local,pc,target)
    assert result['status']=='updated' and result['row_count']==2
    assert result['latest_event']=='Singapore Grand Prix'
    assert Path(result['backup_path']).read_bytes()==before
    assert source.read_bytes()==source_before
    assert pd.read_csv(target).iloc[0].event=='Singapore Grand Prix'
    mtime=target.stat().st_mtime_ns
    again=sync_pc_index(local,pc,target)
    assert again['status']=='current' and target.stat().st_mtime_ns==mtime
    write_index(source,[row(),row('Next weekend','17.10.26 12:00 CET',doc_number='Doc 2',document_url='https://www.fia.com/next.pdf')])
    assert sync_pc_index(local,pc,target)['latest_event']=='Next weekend'


def test_paused_following_custom_paths_and_unavailable_pc_do_not_overwrite(tmp_path):
    local,pc=tmp_path/'desktop',tmp_path/'pc'
    target=local/RELATIVE_INDEX
    write_index(target,[row('Local')]);before=target.read_bytes()
    assert sync_pc_index(local,pc,target)['status']=='pc_index_unavailable'
    assert sync_pc_index(local,pc,target,following=False)['status']=='disabled'
    custom=tmp_path/'custom.csv';write_index(custom,[row('Custom')])
    custom_before=custom.read_bytes()
    write_index(pc/RELATIVE_INDEX,[row()])
    assert sync_pc_index(local,pc,custom)['status']=='custom_source'
    assert custom.read_bytes()==custom_before and target.read_bytes()==before


def test_invalid_pc_index_and_custom_local_columns_preserve_dataset(tmp_path):
    local,pc=tmp_path/'desktop',tmp_path/'pc'
    target,source=local/RELATIVE_INDEX,pc/RELATIVE_INDEX
    write_index(target,[row('Local')]);before=target.read_bytes()
    write_index(source,[{'bad':'data'}])
    assert sync_pc_index(local,pc,target)['status']=='error' and target.read_bytes()==before
    write_index(source,[row()]);write_index(target,[row('Local',personal_note='Keep this column')])
    before=target.read_bytes()
    assert sync_pc_index(local,pc,target)['status']=='custom_columns' and target.read_bytes()==before


def test_app_poll_and_preview_sync_without_a_new_forecast(tmp_path,monkeypatch):
    from portable_app.web_backend import PortableWebApi
    from src.app_services import automation_feed
    local,pc=tmp_path/'desktop',tmp_path/'pc'
    local.mkdir();monkeypatch.chdir(local)
    monkeypatch.setattr(automation_feed,'DEFAULT_PC_WORKSPACE',pc)
    write_index(local/RELATIVE_INDEX,[row('Old','01.01.25 12:00 CET',document_url='https://www.fia.com/old.pdf')])
    write_index(pc/RELATIVE_INDEX,[row()])
    api=PortableWebApi()
    api.base_config['data']['fia_document_index_path']=str(local/RELATIVE_INDEX)
    feed=api.automation_state()
    assert feed['latest'] is None and feed['fia_reference_sync']['status']=='updated'
    preview=api.workbench_data('fia_document_index')
    assert preview['rows'][0]['event']=='Singapore Grand Prix'
    api.automation_preferences(False)
    before=(local/RELATIVE_INDEX).read_bytes()
    write_index(pc/RELATIVE_INDEX,[row('Future','17.10.26 21:00 CET')])
    api.workbench_status()
    assert (local/RELATIVE_INDEX).read_bytes()==before


def test_unchanged_indexes_are_not_reread_on_every_poll(tmp_path,monkeypatch):
    local,pc=tmp_path/'desktop',tmp_path/'pc'
    target,source=local/RELATIVE_INDEX,pc/RELATIVE_INDEX
    write_index(source,[row()])
    assert sync_pc_index(local,pc,target)['status']=='updated'
    reads=[]
    original=Path.read_bytes
    monkeypatch.setattr(Path,'read_bytes',lambda self:reads.append(self) or original(self))
    assert sync_pc_index(local,pc,target)['status']=='current'
    assert reads==[]
    write_index(source,[row(),row('Next weekend','17.10.26 12:00 CET',doc_number='Doc 2',document_url='https://www.fia.com/next.pdf')])
    assert sync_pc_index(local,pc,target)['latest_event']=='Next weekend'
    assert reads

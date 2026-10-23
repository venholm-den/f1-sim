import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.app_services import grid_updates, forecast_automation
from src.data_sources.fia_documents import FIA_DOCUMENT_COLUMNS


def fixture(root, *, saved=(1, 2), latest=(2, 1), status='verified_grid', session='R', seen='2026-06-05T18:00:00Z'):
    folder = root/'forecast'
    folder.mkdir(exist_ok=True)
    features = pd.DataFrame({'Driver':['AAA','BBB'], 'grid_position':saved, 'grid_source':['actual_session_results']*2})
    features.to_csv(folder/'features.csv',index=False)
    path = root/'data/fia_documents/fia_document_index.csv'
    path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for driver, position in zip(['AAA','BBB'], latest):
        row = dict.fromkeys(FIA_DOCUMENT_COLUMNS, '')
        row.update(year=2026,event='Example GP',session=session,document_title='Provisional Starting Grid',
                   document_url='https://www.fia.com/grid.pdf',pdf_sha256='sha',doc_number='Doc 10',
                   driver=driver,grid_position=position,roster_size=2,status=status,
                   published_at='2026-06-05T18:00:00Z',first_seen_at_utc=seen,
                   pit_lane_start=False,withdrawn=False)
        rows.append(row)
    pd.DataFrame(rows).to_csv(path,index=False)
    context={'year':2026,'event':'Example GP','session':'Q','available_sessions':['Q'],
             'data_cutoff_utc':'2026-06-05T19:00:00Z','race_start_utc':'2026-06-07T14:00:00Z'}
    return folder, context


def test_changed_complete_grid_requests_new_forecast_without_editing_saved_features(tmp_path):
    folder, context=fixture(tmp_path)
    before=(folder/'features.csv').read_bytes()
    result=grid_updates.forecast_grid_status(tmp_path,folder,context,cutoff=context['data_cutoff_utc'])
    assert result['status']=='grid_update_available'
    assert result['positions']=={'BBB':1,'AAA':2}
    assert result['refresh_allowed']
    assert (folder/'features.csv').read_bytes()==before


@pytest.mark.parametrize('kwargs', [{'latest':(1,2)}, {'status':'review_required'}, {'session':'S'}, {'seen':'2026-06-05T20:00:00Z'}])
def test_unchanged_unverified_sprint_or_not_yet_seen_grid_does_not_refresh(tmp_path,kwargs):
    folder, context=fixture(tmp_path,**kwargs)
    result=grid_updates.forecast_grid_status(tmp_path,folder,context,cutoff=context['data_cutoff_utc'])
    assert result['status']!='grid_update_available'


def test_mismatched_roster_is_not_partly_applied(tmp_path):
    folder,context=fixture(tmp_path)
    pd.DataFrame({'Driver':['AAA','CCC'],'grid_position':[1,2]}).to_csv(folder/'features.csv',index=False)
    assert grid_updates.forecast_grid_status(tmp_path,folder,context,cutoff=context['data_cutoff_utc'])['status']=='no_verified_grid'


def test_post_race_refresh_and_hindsight_documents_are_blocked(tmp_path):
    folder,context=fixture(tmp_path,seen='2026-06-07T15:00:00Z')
    result=grid_updates.forecast_grid_status(tmp_path,folder,context,cutoff='2026-06-07T16:00:00Z')
    assert not result['refresh_allowed']
    assert result['status']=='no_verified_grid'


def test_revision_validation_requires_applied_fia_grid(tmp_path):
    frozen=tmp_path/'frozen';frozen.mkdir()
    frame=pd.DataFrame({'Driver':['AAA','BBB'],'grid_position':[2,1],'grid_source':['fia_official_grid']*2})
    frame.to_csv(frozen/'features.csv',index=False)
    grid_updates.validate_grid_revision(tmp_path,{'positions':{'AAA':2,'BBB':1}})
    with pytest.raises(ValueError,match='not applied'):
        grid_updates.validate_grid_revision(tmp_path,{'positions':{'AAA':1,'BBB':2}})


def test_automation_creates_one_revision_then_reuses_it(tmp_path, monkeypatch):
    from src.app_services.beta import freeze_snapshot
    folder,context=fixture(tmp_path)
    monkeypatch.setattr(forecast_automation,'next_race',lambda root:dict(context))
    # Two jobs in the same second must be ordered by time, not random ID suffix.
    ids=iter(['ffffffff','00000000'])
    monkeypatch.setattr(forecast_automation,'uuid4',lambda:SimpleNamespace(hex=next(ids)))

    def run(output,job,context=None):
        (output/'forecast_context.json').write_text(json.dumps(context))
        pd.DataFrame({'Driver':['AAA','BBB'],'avg_finish':[1.5,1.5]}).to_csv(output/'simulation_summary.csv',index=False)
        revision=context.get('grid_revision')
        frame=pd.read_csv(folder/'features.csv')
        if revision:
            frame.grid_position=frame.Driver.map(revision['positions'])
            frame.grid_source='fia_official_grid'
        frame.to_csv(output/'features.csv',index=False)
        freeze_snapshot(output,context,now='2026-06-05T19:01:00Z')

    monkeypatch.setattr(forecast_automation,'run_forecast',run)
    first=forecast_automation.run_automated_forecast(tmp_path,n_sims=100)
    original=Path(first['folder'])/'frozen/features.csv'
    before=original.read_bytes()
    second=forecast_automation.run_automated_forecast(tmp_path,n_sims=100)
    assert second['status']=='completed'
    assert original.read_bytes()==before
    job=json.loads((Path(second['folder'])/'job.json').read_text())
    assert job['revision_reason']=='fia_grid_update'
    assert job['supersedes_forecast']==original.parent.parent.name
    third=forecast_automation.run_automated_forecast(tmp_path,n_sims=100)
    assert third['status']=='skipped'
    assert third['folder']==second['folder']
    assert len(list((tmp_path/'outputs/app_runs').glob('*/job.json')))==2

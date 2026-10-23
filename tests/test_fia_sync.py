import json
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from src.data_sources.fia_documents import FIA_DOCUMENT_COLUMNS, merge_fia_document_rows
from src.data_sources.fia_extraction import parse_document, grid_penalty_records
from src.data_sources.fia_sync import derived_rows, refresh
from src.data_sources.fia_asof import context_asof, feature_cutoff
from src.grid import _extract_fia_official_grid, build_grid_features
from tests.test_prediction_data import roster


def row(**changes):
    return {**dict.fromkeys(FIA_DOCUMENT_COLUMNS, ''), 'year':2025, 'event':'GP',
            'session':'R', 'document_type':'starting grid', 'doc_number':'Doc 20',
            'document_title':'Final Starting Grid', 'document_url':'https://www.fia.com/grid.pdf',
            'published_at':'01.03.25 12:00 CET', 'status':'metadata', **changes}


def document(text):
    return {'pages':[{'text':text, 'columns':[]}]}


def decision(text, title='Infringement - Car 1 - PU elements', reason='10 places per component, 40 places total.'):
    return grid_penalty_records(document('No / Driver 1 - Max Verstappen\nDecision '+text+'\nReason '+reason),
        row(document_title=title, document_type='infringement'), roster())


@pytest.mark.parametrize('text,kind,places,target', [
    ('Drop of 40 grid positions in the next Race in which the driver participates.', 'grid_drop',40,'R'),
    ('No penalty applied.', 'no_penalty',None,'R'),
    ('No further action.', 'no_penalty',None,'R'),
    ('Required to start the Sprint from the pit lane.', 'pit_lane',None,'S'),
    ('Required to start the Race from the pit lane.', 'pit_lane',None,'R'),
    ('Start from the back of the grid in the next Race.', 'back_of_grid',None,'R'),
    ('A 5 place grid penalty.', 'grid_drop',5,''),
])
def test_explicit_decision_has_one_sanction_and_its_own_target(text,kind,places,target):
    result = decision(text)
    assert len(result)==1
    assert (result[0]['PenaltyType'],result[0]['GridPlaces'],result[0]['TargetSession'])==(kind,places,target)


def test_reason_and_summons_are_not_sanctions_and_wrong_identity_is_rejected():
    assert decision('A reprimand.',reason='A 10 place grid penalty was considered.')==[]
    assert decision('Drop of 10 grid positions in the next Race.',title='Summons - Car 1')==[]
    with pytest.raises(ValueError,match='contradicts'):
        decision('Drop of 10 grid positions in the next Race.',title='Infringement - Car 4')


def test_plural_grid_footnotes_and_original_decision_are_not_added_twice():
    doc = document('1 1 Max Verstappen\n2 4 Lando Norris\nCars 1 & 4 - 5 place grid penalties - Stewards documents no. 18 & 19')
    result = grid_penalty_records(doc,row(),roster())
    assert [(r['Driver'],r['GridPlaces']) for r in result]==[('VER',5),('NOR',5)]
    note = document('1 1 Max Verstappen\n2 4 Lando Norris\nCar 1 - 40 place grid penalty - Stewards document no. 19')
    rows,_ = derived_rows(note,row(),roster(),'sha','2025-03-01T11:01:00Z')
    original,_ = derived_rows(document('No / Driver 1 - Max Verstappen\nDecision Drop of 40 grid positions in the next Race.\nReason PU'),
        row(doc_number='Doc 19',document_type='infringement',document_title='Infringement - Car 1',
            document_url='https://www.fia.com/decision.pdf'),roster(),'other','2025-03-01T11:01:00Z')
    context = context_asof(merge_fia_document_rows(pd.DataFrame(),rows+original),2025,'GP','2025-03-01T12:00:00Z')
    assert len(context['penalties'])==1
    assert context['penalties'].iloc[0].document_type=='infringement'


def complete_grid():
    rows,_ = derived_rows(document('1 1 Max Verstappen\n2 4 Lando Norris'),row(),roster(),'sha','2025-03-01T11:02:00Z')
    return merge_fia_document_rows(pd.DataFrame(),rows)


def test_both_publication_and_observation_must_precede_cutoff():
    frame = complete_grid()
    assert context_asof(frame,2025,'GP','2025-03-01T11:01:00Z')['official_grid'].empty
    assert len(context_asof(frame,2025,'GP','2025-03-01T11:03:00Z')['official_grid'])==2
    frame.loc[:,'published_at']='01.03.25 14:00 CET'
    assert context_asof(frame,2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty
    frame.loc[:,'published_at']='undated'
    assert context_asof(frame,2025,'GP','2025-03-01T14:00:00Z')['official_grid'].empty
    with pytest.raises(ValueError,match='timezone'):
        context_asof(frame,2025,'GP','2025-03-01 14:00')


def test_truncated_ambiguous_or_new_unparsed_grid_does_not_fall_back():
    frame = complete_grid()
    assert context_asof(frame.iloc[:1],2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty
    other = frame.copy();other['pdf_sha256']='different'
    assert context_asof(pd.concat([frame,other]),2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty
    latest = row(doc_number='Doc 21',published_at='01.03.25 12:30 CET',first_seen_at_utc='2025-03-01T11:31:00Z')
    assert context_asof(merge_fia_document_rows(frame,[latest]),2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty


def test_recalled_grid_is_excluded_only_after_recall_is_observed():
    frame = merge_fia_document_rows(complete_grid(),[row(status='recalled',first_seen_at_utc='2025-03-01T11:30:00Z')])
    assert len(context_asof(frame,2025,'GP','2025-03-01T11:15:00Z')['official_grid'])==2
    assert context_asof(frame,2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty


def test_no_penalty_and_sprint_are_retained_but_not_race_penalties():
    records=[]
    for i, text in enumerate(['No penalty applied.','Required to start the Sprint from the pit lane.']):
        extracted,_ = derived_rows(document('No / Driver 1 - Max Verstappen\nDecision '+text+'\nReason Test'),
            row(document_title='Infringement - Car 1',document_type='infringement',doc_number=f'Doc {i}'),
            roster(),'sha','2025-03-01T11:02:00Z')
        records.extend(extracted)
    assert len(records)==2
    assert context_asof(merge_fia_document_rows(pd.DataFrame(),records),2025,'GP','2025-03-01T12:00:00Z')['penalties'].empty


def test_entry_list_tla_and_car_number_must_match():
    doc = document('1 VER Max Verstappen NED Red Bull\n4 NOR Lando Norris GBR McLaren')
    assert len(parse_document(doc,row(document_title='Entry List'),roster())[1])==2
    with pytest.raises(ValueError,match='Unmapped'):
        parse_document(document('99 VER Max Verstappen NED Red Bull\n4 NOR Lando Norris GBR McLaren'),row(document_title='Entry List'),roster())


def test_font_verified_car_number_superscript_is_removed_without_guessing():
    from scripts.extract_fia_pdf_text import without_car_number_footnotes
    base={'text':'1','x0':40,'x1':46,'top':100,'bottom':111,'size':11}
    marker={'text':'2','x0':46.1,'x1':50,'top':99,'bottom':106,'size':7}
    fake=Mock();fake.width=600;fake.extract_words.return_value=[base,marker]
    fake.filter.return_value.extract_text.return_value='1 Max Verstappen NED Red Bull'
    clean,removed=without_car_number_footnotes(fake)
    assert removed[0]['base']=='1' and removed[0]['marker']=='2'
    predicate=fake.filter.call_args.args[0]
    assert not predicate({'object_type':'char',**marker})
    assert predicate({'object_type':'char',**base})
    doc=document('12 Max Verstappen NED Red Bull\n4 Lando Norris GBR McLaren')
    with pytest.raises(ValueError,match='Unmapped'):
        parse_document(doc,row(document_title='Entry List'),roster())
    doc['pages'][0]['entry_text']=clean+'\n4 Lando Norris GBR McLaren'
    assert len(parse_document(doc,row(document_title='Entry List'),roster())[1])==2


def test_same_size_digit_is_never_stripped_as_a_footnote():
    from scripts.extract_fia_pdf_text import without_car_number_footnotes
    fake=Mock();fake.width=600
    fake.extract_words.return_value=[{'text':'63','x0':40,'x1':52,'top':100,'bottom':111,'size':11},
                                     {'text':'1','x0':52.1,'x1':58,'top':100,'bottom':111,'size':11}]
    fake.filter.return_value.extract_text.return_value='631 George Russell'
    assert without_car_number_footnotes(fake)[1]==[]


def test_unparsed_changed_grid_is_not_replaced_by_an_older_verified_pdf():
    frame=merge_fia_document_rows(complete_grid(),[row(status='review_required',
        pdf_sha256='new_sha',extraction_version='fia_v2',first_seen_at_utc='2025-03-01T11:30:00Z')])
    assert len(context_asof(frame,2025,'GP','2025-03-01T11:15:00Z')['official_grid'])==2
    assert context_asof(frame,2025,'GP','2025-03-01T12:00:00Z')['official_grid'].empty


def test_incomplete_official_roster_cannot_partially_override_qualifying():
    from tests.test_grid import FakeQualifyingSession
    features=pd.DataFrame({'Driver':['RUS','HAM','ANT','LEC'],'Team':['A','A','A','A'],'model_pace':[0,.1,.2,.3]})
    context={'official_grid':pd.DataFrame({'Driver':['RUS','HAM'],'fia_grid_position':[2,1]})}
    result=build_grid_features(features,pd.DataFrame(),current_session_type='Q',current_session=FakeQualifyingSession(),fia_context=context)
    assert result.set_index('Driver').loc['RUS','grid_position']==1
    assert result.grid_source.eq('actual_session_results').all()


def test_explicit_pit_lane_and_withdrawal_are_not_pole_position():
    rows,_ = derived_rows(document('1 1 Max Verstappen\nDRIVERS REQUIRED TO START FROM THE PIT LANE\n4 Lando Norris'),
        row(),roster(),'sha','2025-03-01T11:02:00Z')
    context = context_asof(merge_fia_document_rows(pd.DataFrame(),rows),2025,'GP','2025-03-01T12:00:00Z')
    grid = _extract_fia_official_grid(context).set_index('Driver')
    assert grid.loc['NOR','fia_grid_position']==3 and grid.loc['NOR','fia_pit_lane_start']
    rows,_ = derived_rows(document('1 1 Max Verstappen\nCar 4 - Withdrawn - Stewards document no. 5'),
        row(),roster(),'sha','2025-03-01T11:02:00Z')
    context = context_asof(merge_fia_document_rows(pd.DataFrame(),rows),2025,'GP','2025-03-01T12:00:00Z')
    assert len(context['official_grid'])==2
    assert _extract_fia_official_grid(context).empty


def listing_html():
    return '<html><div class="event-title">GP</div><li class="document-row"><a href="/grid.pdf"><div class="title">Final Starting Grid</div></a><div class="doc-number">20</div><div class="published">01.03.25 12:00 CET</div></li></html>'


def mocked_get(url,**kwargs):
    response=Mock()
    response.text=listing_html()
    response.content=b'%PDF-test'
    return response


def test_refresh_is_atomic_backed_up_throttled_and_preserves_version_observation(tmp_path):
    directory=tmp_path/'data/fia_documents';directory.mkdir(parents=True)
    index=directory/'fia_document_index.csv'
    pd.DataFrame([row(document_title='Old metadata',document_url='https://www.fia.com/old.pdf')]).to_csv(index,index=False)
    before=index.read_bytes()
    kwargs=dict(force=True,year=2025,get=mocked_get,roster_loader=lambda *a:roster(),
        extractor=lambda *a:document('1 1 Max Verstappen\n2 4 Lando Norris'))
    result=refresh(tmp_path,now='2025-03-01T11:02:00Z',**kwargs)
    assert result['status']=='completed' and result['review_required']==0
    assert __import__('pathlib').Path(result['index_backup']).read_bytes()==before
    assert len(pd.read_csv(index))==4
    later=refresh(tmp_path,now='2025-03-01T11:04:00Z',**kwargs)
    context=context_asof(pd.read_csv(index).fillna(''),2025,'GP','2025-03-01T11:03:00Z')
    assert len(context['official_grid'])==2  # rechecking must not reset first seen
    (tmp_path/'config').mkdir();(tmp_path/'config/fia_sync.json').write_text('{"enabled":true}')
    assert refresh(tmp_path,now='2025-03-01T11:05:00Z')['status']=='not_due'
    assert later['rows_added']==0


def test_refresh_failure_and_missing_pdf_runtime_preserve_metadata(tmp_path):
    directory=tmp_path/'data/fia_documents';directory.mkdir(parents=True)
    index=directory/'fia_document_index.csv'
    pd.DataFrame([row()]).to_csv(index,index=False)
    before=index.read_bytes()
    response=Mock();response.text='<html>unavailable</html>'
    result=refresh(tmp_path,force=True,year=2025,now='2025-03-01T11:02:00Z',get=lambda *a,**k:response)
    assert result['status']=='failed' and index.read_bytes()==before
    def missing(*a):
        raise RuntimeError('PDF parser unavailable')
    result=refresh(tmp_path,force=True,year=2025,now='2025-03-01T11:03:00Z',get=mocked_get,
                   roster_loader=lambda *a:roster(),extractor=missing)
    assert result['status']=='completed' and result['review_required']==1
    assert 'verified_grid' not in pd.read_csv(index).status.values


def test_historical_cutoff_uses_session_end_and_live_cutoff_uses_now():
    session=SimpleNamespace(event={'Session5':'Race','Session5DateUtc':'2025-03-02T12:00:00Z'},
                            t0_date='2025-03-01T10:00:00Z',session_status=pd.DataFrame({'Time':[pd.Timedelta(hours=1)]}))
    assert pd.Timestamp(feature_cutoff(session,{},now='2025-03-01T11:02:00Z'))==pd.Timestamp('2025-03-01T11:02:00Z')
    assert pd.Timestamp(feature_cutoff(session,{},now='2025-03-03T12:00:00Z'))==pd.Timestamp('2025-03-01T11:00:00Z')
    with pytest.raises(ValueError,match='future'):
        feature_cutoff(session,{},'2025-03-04T12:00:00Z',now='2025-03-03T12:00:00Z')

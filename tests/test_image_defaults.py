import copy
from unittest.mock import patch
import pytest
import lyra_backend as camera


def settings():
    result={name:{'cur':0,'min':-100,'max':100,'step':1,'def':99,'isAuto':2,'enable':1}
            for name in camera.IMAGE_SETTINGS}
    result['white-balance']={'cur':5000,'min':2800,'max':7000,'step':1,'def':6500,'isAuto':1,'enable':1}
    result['shutter']={'cur':1,'def':1,'list':['1/60','1/120'],'isAuto':2,'enable':1}
    result['iso']={'cur':2,'def':2,'list':['100','250','1600'],'isAuto':1,'enable':1}
    result['anti-flicker']={'cur':2,'def':2,'list':['OFF','50Hz','60Hz'],'isAuto':2,'enable':1}
    result['brightness']['enable']=2
    return result


def read_fn(state):
    def read(name):
        return {'module':'C4502'} if name=='info' else copy.deepcopy(state[name])
    return read


def writer_fn(state):
    def apply(name,value,automatic=False):
        if name=='anti-flicker' and value==0:
            state['shutter']={'cur':0,'def':0,'list':['1/30','1/60','1/120'],'isAuto':1,'enable':1}
            state['brightness']['enable']=1
        state[name]['cur']=value
        if name in ('white-balance','shutter','iso'):
            state[name]['isAuto']=0 if automatic else 1
        return copy.deepcopy(state[name])
    return apply


def test_reset_restores_initial_auto_values_instead_of_mutable_def_fields():
    state=settings()
    with patch.object(camera,'read',side_effect=read_fn(state)),\
         patch.object(camera,'apply',side_effect=writer_fn(state)) as apply,\
         patch.object(camera,'snapshot',return_value={}):
        result=camera.reset_image_defaults()
    assert len(result['settings'])==8
    assert apply.call_args_list[0].args==('anti-flicker',0,False)
    assert not any(call.args[0] in ('zoom','focus-mode') for call in apply.call_args_list)
    assert state['white-balance']['cur']==5100 and state['white-balance']['isAuto']==0
    assert state['iso']['cur']==1 and state['iso']['isAuto']==0
    assert state['shutter']['cur']==1 and state['shutter']['isAuto']==0
    assert state['brightness']['cur']==0 and state['sharpness']['cur']==50
    assert not result['skipped']


def test_initial_profile_is_based_on_original_readings_not_current_iso_default():
    profile=camera.initial_profile()['settings']
    assert profile['iso']=={'value':'250','automatic':True}
    assert profile['anti-flicker']=={'value':'OFF','automatic':False}
    assert set(profile)==set(camera.IMAGE_SETTINGS)


def test_profile_maps_list_labels_after_dependency_changes():
    state=settings()
    assert camera.profile_value('shutter',state['shutter'],{'value':'1/60','automatic':False})==0
    writer_fn(state)('anti-flicker',0,False)
    assert camera.profile_value('shutter',state['shutter'],{'value':'1/60','automatic':True})==1


def test_wrong_model_is_rejected_without_writes():
    with patch.object(camera,'read',return_value={'module':'other-model'}),patch.object(camera,'apply') as apply:
        with pytest.raises(camera.CameraError,match='does not match'):camera.reset_image_defaults()
        apply.assert_not_called()


def test_partial_failure_rolls_back_original_image_state():
    state=settings();before=copy.deepcopy(state)
    with patch.object(camera,'read',side_effect=read_fn(state)),\
         patch.object(camera,'apply',side_effect=[state['anti-flicker'],RuntimeError('disconnected')]),\
         patch.object(camera,'restore_image_state') as restore:
        with pytest.raises(camera.CameraError,match='Previous image settings restored'):
            camera.reset_image_defaults()
    restore.assert_called_once_with(before)

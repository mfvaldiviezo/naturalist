"""Actualizador TD exploratorio usando ColightNet autentica de LibSignal.

Importante: NO es la clase CoLightAgent ni el entrenador nativo LibSignal.
No afirma reproduccion SOTA. Arquitectura sin ediciones AST originales.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import random
import numpy as np

def require(ok,why):
    if not ok:raise RuntimeError(why)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def prepare_original_model(plan,lib,seed):
    """Solo fuentes fijadas; sin importar el agente LibSignal ni CityFlow."""
    import torch
    import yaml
    from h12_18_colight_loader import load_original_colight_net
    lib=Path(lib).resolve(strict=True)
    provenance=plan['libsignal']
    require(sha(lib/'configs/tsc/colight.yml')==provenance['config_worktree_sha256'],
            'YAML LibSignal alterado')
    cls,origin=load_original_colight_net(lib,provenance['worktree_sha256'])
    require(origin['upstream_commit']==provenance['commit'] and
            origin['upstream_blob_sha1']==provenance['blob_sha1'],
            'No se instanció arquitectura CoLight auditada')
    config=yaml.safe_load((lib/'configs/tsc/colight.yml').read_text(encoding='utf8'))
    base=yaml.safe_load((lib/'configs/tsc/base.yml').read_text(encoding='utf8'))
    arch_keys=('NODE_EMB_DIM','N_LAYERS','INPUT_DIM','OUTPUT_DIM',
               'NUM_HEADS','NODE_LAYER_DIMS_EACH_HEAD','OUTPUT_LAYERS')
    kwargs={key:config['model'][key] for key in arch_keys}
    kwargs['batch_size']=1
    torch.manual_seed(seed)
    model=cls(4,2,[2]*12,**kwargs)
    model=model.cpu()
    require(base['model']['learning_rate']==0.001 and base['model']['gamma']==0.95 and
            base['model']['grad_clip']==5.,'Hiperparametros TD distintos LibSignal base')
    return model,origin

def _graph(row,edge):
    import torch
    from torch_geometric.data import Data
    a=np.asarray(row,dtype=np.float32)
    require(a.shape==(12,4) and np.isfinite(a).all(),'Observacion mal formada')
    return Data(x=torch.from_numpy(a),edge_index=edge)

def td_step(model,target,optimizer,samples,edge,gamma=.95,clip=5.):
    import torch
    from torch_geometric.data import Batch
    model.train()
    # No copies of the model architecture: all trainable layers from LibSignal.
    batch=Batch.from_data_list([_graph(x['obs_12x4'],edge) for x in samples])
    batch_next=Batch.from_data_list([_graph(x['next_obs_12x4'],edge) for x in samples])
    actions=torch.tensor([x for r in samples for x in r['requested_actions']],dtype=torch.int64)
    rewards=torch.tensor([x for r in samples for x in r['reward_per_node']],dtype=torch.float32)
    dones=torch.tensor([float(r['done']) for r in samples for _ in range(12)],dtype=torch.float32)
    # Upstream DQN target + explicit episodic truncation terminal mask.
    with torch.no_grad():
        qnext=target(x=batch_next.x,edge_index=batch_next.edge_index,train=False)
        require(qnext.shape==(12*len(samples),2),'Next Q dimensión incorrecta')
        y=rewards+gamma*(1.-dones)*qnext.max(dim=1).values
    q=model(x=batch.x,edge_index=batch.edge_index,train=True)
    require(q.shape==(12*len(samples),2),'Q dimensión incorrecta')
    chosen=q.gather(1,actions.view(-1,1)).squeeze(1)
    loss=torch.nn.functional.mse_loss(chosen,y)
    require(torch.isfinite(loss).item(),'Loss no finita')
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    gnorm=torch.nn.utils.clip_grad_norm_(model.parameters(),clip)
    require(torch.isfinite(gnorm).item(),'Gradientes no finitos')
    optimizer.step()
    return {'loss':float(loss.detach().item()),'gradient_norm':float(gnorm.item()),
            'batch_transitions':len(samples),'batch_node_transitions':12*len(samples)}

def _before_after(before,model):
    import torch
    diffs=[]
    for n,p in model.named_parameters():
        require(torch.isfinite(p).all().item(),'Parametros no finitos '+n)
        d=torch.abs(p.detach()-before[n]);diffs.append(float(d.max().item()))
    mx=max(diffs)
    require(mx>0 and math.isfinite(mx),'No se observaron actualizaciones de pesos')
    return mx

def gradient_probe(plan,lib,seed):
    import torch
    model,origin=prepare_original_model(plan,lib,seed)
    target=deepcopy(model).eval()
    optimizer=torch.optim.RMSprop(model.parameters(),lr=.001,alpha=.9,centered=False,eps=1e-7)
    edge=torch.tensor(plan['graph']['edge_index'],dtype=torch.long)
    before={n:p.detach().clone() for n,p in model.named_parameters()}
    data=[]
    for k in range(4):
        data.append({'obs_12x4':[[float((k+i+j)%7) for j in range(4)] for i in range(12)],
                    'next_obs_12x4':[[float((k+i+j+1)%7) for j in range(4)] for i in range(12)],
                    'requested_actions':[(k+i)%2 for i in range(12)],
                    'reward_per_node':[-float((k+i)%3) for i in range(12)],'done':k==3})
    details=td_step(model,target,optimizer,data,edge)
    delta=_before_after(before,model)
    return {'result':'H12_19_ORIGINAL_COLIGHTNET_TD_GRADIENT_PROBE_OK',
            'architecture_provenance':origin,'input_shape':[12,4],
            'output_shape':[12,2],'loss':details['loss'],
            'gradient_norm':details['gradient_norm'],
            'max_parameter_delta':delta,
            'saved_checkpoint':False,'SUMO':'NOT_RUN',
            'upstream_trainer':'NOT_INVOKED','full_CoLight_SOTA':'NOT_CERTIFIED'}

def train_offpolicy(rows,plan,lib,a,out):
    import torch
    from copy import deepcopy
    model,origin=prepare_original_model(plan,lib,a.seed)
    target=deepcopy(model).eval()
    optimizer=torch.optim.RMSprop(model.parameters(),lr=.001,alpha=.9,centered=False,eps=1e-7)
    edge=torch.tensor(plan['graph']['edge_index'],dtype=torch.long)
    before={n:p.detach().clone() for n,p in model.named_parameters()}
    rng=random.Random(a.seed+1919)
    updates=[]
    for u in range(a.updates):
        indices=rng.sample(range(len(rows)),k=a.batch_size)
        detail=td_step(model,target,optimizer,[rows[i] for i in indices],edge)
        detail['iteration']=u+1;detail['replay_indices']=indices
        updates.append(detail)
        if (u+1)%4==0:target.load_state_dict(model.state_dict())
    delta=_before_after(before,model)
    checkpoint=Path(out)/'colight_network_td_pilot_only.pt'
    require(not checkpoint.exists(),'Nunca reemplazar checkpoint')
    torch.save({'state_dict':model.state_dict(),
                'contract':{'model':'LibSignal original ColightNet; isolated AST',
                            'tag':'TD_PILOT_ONLY_NOT_SOTA',
                            'node_order':plan['graph']['node_order'],
                            'libsignal_commit':origin['upstream_commit'],
                            'libsignal_blob':origin['upstream_blob_sha1'],
                            'input_shape':[12,4],'output_actions_per_node':2,
                            'torch_version':str(torch.__version__),
                            'no_colight_agent_trainer':True,
                            'no_neural_action_on_sumo':True}},checkpoint)
    require(checkpoint.is_file() and checkpoint.stat().st_size>0,'Checkpoint no grabado')
    # Verificacion de serializacion inmediata, pero NO acredita inferencia SOTA.
    test_load=torch.load(checkpoint,map_location='cpu',weights_only=True)
    require(test_load['contract']['tag']=='TD_PILOT_ONLY_NOT_SOTA',
            'Etiqueta checkpoint inesperada')
    state=test_load['state_dict']
    require(state.keys()==model.state_dict().keys() and
            all(torch.equal(state[k],model.state_dict()[k]) for k in state),
            'Checkpoint no conserva exactamente el estado del modelo')
    return {'architecture':origin,'update_count':len(updates),
            'losses':[u['loss'] for u in updates],
            'updates':updates,'gradient_probe':'REAL_SIMULATION_REPLAY',
            'max_parameter_delta':delta,'checkpoint_file':str(checkpoint),
            'checkpoint_sha256':sha(checkpoint),
            'checkpoint_bytes':checkpoint.stat().st_size,
            'checkpoint_status':'EXPLORATORY_TD_PILOT_NEVER_FULL_SOTA',
            'upstream_colight_agent_training':'NOT_EXECUTED',
            'environment_actions_from_network':'NEVER'}
